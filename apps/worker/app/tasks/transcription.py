"""转写任务 - Celery Task 封装。

提供异步转写任务的注册和执行函数。
"""
from __future__ import annotations

import logging

from domain.schemas.transcript import TranscriptResult
from model_adapters import resolve_audio_asset_path

from ..celery_app import get_celery_app, is_async_available
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry
from ._base import update_job_result, update_job_status

logger = logging.getLogger(__name__)


def _run_transcription_sync(
    job_id: str,
    asset_name: str,
    model_key: str = "funasr-nano",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = False,
    itn: bool = True,
) -> TranscriptResult:
    """同步执行转写任务（内部实现）。

    此函数会被 Celery task 包装后执行，也会作为同步回退使用。
    """
    registry = get_worker_registry()
    registry.require_available(model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))

    import copy

    adapter = copy.copy(registry.get_asr(model_key))
    if hotwords and hasattr(adapter, "hotwords"):
        adapter.hotwords = hotwords
    if hasattr(adapter, "language"):
        adapter.language = language
    if hasattr(adapter, "vad_enabled"):
        adapter.vad_enabled = vad_enabled
    if hasattr(adapter, "itn"):
        adapter.itn = itn

    return adapter.transcribe(asset)


def _adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))


def execute_transcription_task(
    job_id: str,
    asset_name: str,
    model_key: str = "funasr-nano",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = False,
    itn: bool = True,
) -> TranscriptResult:
    """执行转写任务（Celery Worker 入口）。

    更新任务状态为 running，执行转写，然后更新结果。
    此函数会被 Celery 自动调用。
    """
    # 更新状态为 running
    update_job_status(job_id, "running")

    try:
        result = _run_transcription_sync(
            job_id=job_id,
            asset_name=asset_name,
            model_key=model_key,
            hotwords=hotwords,
            language=language,
            vad_enabled=vad_enabled,
            itn=itn,
        )
        update_job_result(job_id, result=result, status="succeeded")
        return result
    except Exception as e:
        logger.error(f"任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


# 获取 Celery app 并注册 task
_celery_app = None
_run_transcription_task = None


def _init_celery_task():
    global _celery_app, _run_transcription_task
    if _run_transcription_task is not None:
        return _run_transcription_task

    try:
        celery = get_celery_app()
        if celery is not None:
            _run_transcription_task = celery.task(execute_transcription_task, name="apps.worker.app.tasks.transcription.execute_transcription_task")
            logger.info("Celery 转写任务已注册: execute_transcription_task")
            return _run_transcription_task
    except Exception as e:
        logger.warning(f"注册 Celery 转写任务失败: {e}")

    return None


def get_transcription_task():
    """获取 Celery task（可能为 None）。"""
    global _run_transcription_task
    if _run_transcription_task is None:
        _init_celery_task()
    return _run_transcription_task


def run_transcription(
    job_id: str,
    asset_name: str,
    model_key: str = "funasr-nano",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = False,
    itn: bool = True,
) -> TranscriptResult:
    """运行转写任务。

    根据配置自动选择同步或异步执行：
    - 异步模式：推送到 Celery 队列，返回空结果（Worker 会更新）
    - 同步模式：直接执行转写

    Args:
        job_id: 任务 ID
        asset_name: 音频资产名
        model_key: 模型键（默认 funasr-nano）
        hotwords: 热词列表
        language: 语言
        vad_enabled: 是否启用 VAD
        itn: 是否启用 ITN

    Returns:
        异步模式: 空结果（TranscriptResult with empty text）
        同步模式: 实际转写结果
    """
    # 如果启用了 Celery，尝试异步执行
    if is_async_available():
        task = get_transcription_task()
        if task is not None:
            try:
                # 异步执行 - 推送到队列
                task.apply_async(
                    args=[job_id, asset_name, model_key],
                    kwargs={
                        "hotwords": hotwords,
                        "language": language,
                        "vad_enabled": vad_enabled,
                        "itn": itn,
                    },
                )
                logger.info(f"任务 {job_id} 已提交到队列（转写）")
                # 返回空结果，Worker 会更新实际结果
                return TranscriptResult(text="", language=language, segments=[])
            except Exception as e:
                logger.warning(f"异步提交失败，回退到同步执行: {e}")

    # 同步执行（回退）
    logger.info(f"任务 {job_id} 同步执行（转写）")
    return _run_transcription_sync(
        job_id=job_id,
        asset_name=asset_name,
        model_key=model_key,
        hotwords=hotwords,
        language=language,
        vad_enabled=vad_enabled,
        itn=itn,
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
    task = get_transcription_task()
    if task is not None:
        return task

    # 没有 Celery 时，返回带 apply_async 的同步包装器
    return _SyncApplyWrapper(execute_transcription_task)


run_transcription_task = _get_task_or_wrapper()
