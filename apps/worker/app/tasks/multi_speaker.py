"""多人转写任务 - Celery Task 封装。

提供异步多人转写任务的注册和执行函数。
"""
from __future__ import annotations

import logging

from domain.schemas.transcript import TranscriptMetadata, TranscriptResult, TranscriptTimeline
from model_adapters import resolve_audio_asset_path

from ..celery_app import get_celery_app, is_async_available
from ..pipelines.alignment import (
    align_transcript_with_speakers,
    build_display_speaker_timeline,
    build_exclusive_speaker_timeline,
)
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry
from ._base import update_job_result, update_job_status

logger = logging.getLogger(__name__)


def _run_multi_speaker_transcription_sync(
    job_id: str,
    asset_name: str,
    asr_model_key: str = "funasr-nano",
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = True,
    itn: bool = True,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    """同步执行多人转写任务（内部实现）。

    参数：
        job_id: 任务 ID
        asset_name: 音频资产名
        asr_model_key: ASR 模型键（默认 funasr-nano）
        diarization_model_key: 说话人分离模型键（默认 3dspeaker-diarization）
        hotwords: 热词列表，用于提升专业术语识别率
        language: 语言/方言（zh-cn / en / yue / Sichuan 等）
        vad_enabled: 是否启用 VAD（语音活动检测，过滤静音噪声）
        itn: 是否启用逆文本正则化（数字/日期/货币格式化）
        num_speakers: 已知说话人数量（用于聚类提示，None 则自动估计）
    """
    registry = get_worker_registry()
    registry.require_available(asr_model_key)
    registry.require_available(diarization_model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))

    # 配置 ASR 适配器
    asr_adapter = registry.get_asr(asr_model_key)
    if hotwords and hasattr(asr_adapter, "hotwords"):
        asr_adapter.hotwords = hotwords
    if hasattr(asr_adapter, "language"):
        asr_adapter.language = language
    if hasattr(asr_adapter, "vad_enabled"):
        asr_adapter.vad_enabled = vad_enabled
    if hasattr(asr_adapter, "itn"):
        asr_adapter.itn = itn

    # 运行 ASR 转写
    transcript = asr_adapter.transcribe(asset)

    # 运行说话人分离（VAD + CAM++ + 谱聚类）
    diarization_adapter = registry.get_diarization(diarization_model_key)
    if hasattr(diarization_adapter, "num_speakers"):
        diarization_adapter.num_speakers = num_speakers
    if hasattr(diarization_adapter, "min_speakers"):
        diarization_adapter.min_speakers = min_speakers
    if hasattr(diarization_adapter, "max_speakers"):
        diarization_adapter.max_speakers = max_speakers
    diarization_segments = diarization_adapter.diarize(asset)

    # 对齐转写文本与说话人标签
    aligned = align_transcript_with_speakers(transcript, diarization_segments)
    exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)
    display_segments = build_display_speaker_timeline(aligned.segments, exclusive_segments or diarization_segments)
    metadata = TranscriptMetadata(
        diarization_model=diarization_model_key,
        alignment_source="exclusive" if exclusive_segments else "regular",
        timelines=[
            TranscriptTimeline(label="Regular diarization", source="regular", segments=diarization_segments),
            TranscriptTimeline(
                label="Exclusive alignment timeline",
                source="exclusive",
                segments=exclusive_segments or diarization_segments,
            ),
            TranscriptTimeline(
                label="Display speaker timeline",
                source="display",
                segments=display_segments,
            ),
        ],
    )
    return aligned.model_copy(update={"metadata": metadata})


def _adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))


def execute_multi_speaker_transcription_task(
    job_id: str,
    asset_name: str,
    asr_model_key: str = "funasr-nano",
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = True,
    itn: bool = True,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    """执行多人转写任务（Celery Worker 入口）。

    更新任务状态为 running，执行转写，然后更新结果。
    此函数会被 Celery 自动调用。
    """
    # 更新状态为 running
    update_job_status(job_id, "running")

    try:
        result = _run_multi_speaker_transcription_sync(
            job_id=job_id,
            asset_name=asset_name,
            asr_model_key=asr_model_key,
            diarization_model_key=diarization_model_key,
            hotwords=hotwords,
            language=language,
            vad_enabled=vad_enabled,
            itn=itn,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        update_job_result(job_id, result=result, status="succeeded")
        return result
    except Exception as e:
        logger.error(f"多人转写任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


# 获取 Celery app 并注册 task
_celery_app = None
_run_multi_speaker_task = None


def _init_celery_task():
    global _celery_app, _run_multi_speaker_task
    if _run_multi_speaker_task is not None:
        return _run_multi_speaker_task

    try:
        celery = get_celery_app()
        if celery is not None:
            _run_multi_speaker_task = celery.task(
                execute_multi_speaker_transcription_task,
                name="apps.worker.app.tasks.multi_speaker.execute_multi_speaker_transcription_task",
            )
            logger.info("Celery 多人转写任务已注册: execute_multi_speaker_transcription_task")
            return _run_multi_speaker_task
    except Exception as e:
        logger.warning(f"注册 Celery 多人转写任务失败: {e}")

    return None


def get_multi_speaker_task():
    """获取 Celery task（可能为 None）。"""
    global _run_multi_speaker_task
    if _run_multi_speaker_task is None:
        _init_celery_task()
    return _run_multi_speaker_task


def run_multi_speaker_transcription(
    job_id: str,
    asset_name: str,
    asr_model_key: str = "funasr-nano",
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = True,
    itn: bool = True,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    """运行多人转写任务。

    根据配置自动选择同步或异步执行：
    - 异步模式：推送到 Celery 队列，返回空结果（Worker 会更新）
    - 同步模式：直接执行转写

    Args:
        job_id: 任务 ID
        asset_name: 音频资产名
        asr_model_key: ASR 模型键
        diarization_model_key: 说话人分离模型键
        hotwords: 热词列表
        language: 语言
        vad_enabled: 是否启用 VAD
        itn: 是否启用 ITN
        num_speakers: 已知说话人数量
        min_speakers: 最少说话人数量
        max_speakers: 最多说话人数量

    Returns:
        异步模式: 空结果（TranscriptResult with empty text）
        同步模式: 实际转写结果
    """
    # 如果启用了 Celery，尝试异步执行
    if is_async_available():
        task = get_multi_speaker_task()
        if task is not None:
            try:
                # 异步执行 - 推送到队列
                task.apply_async(
                    args=[job_id, asset_name, asr_model_key, diarization_model_key],
                    kwargs={
                        "hotwords": hotwords,
                        "language": language,
                        "vad_enabled": vad_enabled,
                        "itn": itn,
                        "num_speakers": num_speakers,
                        "min_speakers": min_speakers,
                        "max_speakers": max_speakers,
                    },
                )
                logger.info(f"多人转写任务 {job_id} 已提交到队列")
                # 返回空结果，Worker 会更新实际结果
                return TranscriptResult(text="", language=language, segments=[])
            except Exception as e:
                logger.warning(f"异步提交失败，回退到同步执行: {e}")

    # 同步执行（回退）
    logger.info(f"多人转写任务 {job_id} 同步执行")
    return _run_multi_speaker_transcription_sync(
        job_id=job_id,
        asset_name=asset_name,
        asr_model_key=asr_model_key,
        diarization_model_key=diarization_model_key,
        hotwords=hotwords,
        language=language,
        vad_enabled=vad_enabled,
        itn=itn,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )


# 为了兼容旧代码，提供 task 对象
class _SyncApplyWrapper:
    """同步回退包装器，提供与 Celery task 相同的 apply_async 接口。

    当 Celery 不可用时，job_service.py 调用 .apply_async() 会触发此包装器
    的 apply_async()，它会直接执行同步任务而不是推送到队列。
    """

    def __init__(self, sync_func):
        self._sync_func = sync_func

    def apply_async(self, args=None, kwargs=None):
        """同步执行任务（Celery 不可用时的回退）。

        与 Celery task.apply_async() 签名兼容，但直接在当前线程执行。
        """
        return self._sync_func(*(args or []), **(kwargs or {}))


def _get_task_or_wrapper():
    """获取 task 或兼容 wrapper。

    返回值始终有 .apply_async() 方法：
    - 有 Celery 时：返回 Celery task 对象（自有 apply_async）
    - 无 Celery 时：返回 _SyncApplyWrapper（也有 apply_async）
    """
    task = get_multi_speaker_task()
    if task is not None:
        return task

    # 没有 Celery 时，返回带 apply_async 的同步包装器
    return _SyncApplyWrapper(execute_multi_speaker_transcription_task)


run_multi_speaker_transcription_task = _get_task_or_wrapper()
