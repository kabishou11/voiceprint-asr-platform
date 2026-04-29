"""多人转写任务 - Celery Task 封装。

提供异步多人转写任务的注册和执行函数。
ASR 与 Diarization 默认并行执行以减少总耗时。
"""
from __future__ import annotations

import copy
import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from domain.schemas.transcript import (
    Segment,
    TranscriptMetadata,
    TranscriptResult,
    TranscriptTimeline,
    VoiceprintMatchCandidate,
    VoiceprintSpeakerMatch,
)
from model_adapters import AudioAsset, resolve_audio_asset_path

from ..celery_app import get_celery_app, is_async_available
from ..pipelines.alignment import (
    align_transcript_with_speakers,
    build_display_speaker_timeline,
    build_exclusive_speaker_timeline,
    canonicalize_speaker_labels,
)
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry
from ._base import update_job_result, update_job_status

logger = logging.getLogger(__name__)

PARALLEL_ASR_DIARIZATION = os.environ.get("PARALLEL_ASR_DIARIZATION", "1") == "1"


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
    voiceprint_scope_mode: str = "none",
    voiceprint_group_id: str | None = None,
    voiceprint_profile_ids: list[str] | None = None,
) -> TranscriptResult:
    """同步执行多人转写任务（内部实现）。

    ASR 与 Diarization 默认并行执行（可通过 PARALLEL_ASR_DIARIZATION=0 关闭）。

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
        min_speakers: 最少说话人数
        max_speakers: 最多说话人数
    """
    registry = get_worker_registry()
    registry.require_available(asr_model_key)
    registry.require_available(diarization_model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))

    asr_adapter = copy.copy(registry.get_asr(asr_model_key))
    if hotwords and hasattr(asr_adapter, "hotwords"):
        asr_adapter.hotwords = hotwords
    if hasattr(asr_adapter, "language"):
        asr_adapter.language = language
    if hasattr(asr_adapter, "vad_enabled"):
        asr_adapter.vad_enabled = vad_enabled
    if hasattr(asr_adapter, "itn"):
        asr_adapter.itn = itn

    diarization_adapter = copy.copy(registry.get_diarization(diarization_model_key))
    if hasattr(diarization_adapter, "num_speakers"):
        diarization_adapter.num_speakers = num_speakers
    if hasattr(diarization_adapter, "min_speakers"):
        diarization_adapter.min_speakers = min_speakers
    if hasattr(diarization_adapter, "max_speakers"):
        diarization_adapter.max_speakers = max_speakers

    if PARALLEL_ASR_DIARIZATION:
        logger.info(f"任务 {job_id} 并行执行 ASR + Diarization")
        with ThreadPoolExecutor(max_workers=2) as executor:
            asr_future = executor.submit(asr_adapter.transcribe, asset)
            dia_future = executor.submit(diarization_adapter.diarize, asset)
            transcript = asr_future.result()
            diarization_segments = dia_future.result()
    else:
        logger.info(f"任务 {job_id} 串行执行 ASR + Diarization")
        transcript = asr_adapter.transcribe(asset)
        diarization_segments = diarization_adapter.diarize(asset)

    diarization_segments = canonicalize_speaker_labels(diarization_segments)
    aligned = align_transcript_with_speakers(transcript, diarization_segments)
    exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)
    display_segments = build_display_speaker_timeline(
        aligned.segments,
        exclusive_segments or diarization_segments,
    )
    voiceprint_matches = _build_voiceprint_matches(
        registry=registry,
        asset=asset,
        segments=aligned.segments,
        scope_mode=voiceprint_scope_mode,
        group_id=voiceprint_group_id,
        profile_ids=voiceprint_profile_ids,
    )
    metadata = TranscriptMetadata(
        diarization_model=diarization_model_key,
        alignment_source="exclusive" if exclusive_segments else "regular",
        voiceprint_matches=voiceprint_matches,
        timelines=[
            TranscriptTimeline(
                label="Regular diarization",
                source="regular",
                segments=diarization_segments,
            ),
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


def _build_voiceprint_matches(
    *,
    registry,
    asset: AudioAsset,
    segments: list[Segment],
    scope_mode: str,
    group_id: str | None,
    profile_ids: list[str] | None,
) -> list[VoiceprintSpeakerMatch]:
    if scope_mode == "none":
        return []

    candidate_ids, display_names = _resolve_voiceprint_candidates(scope_mode, group_id, profile_ids)
    if not candidate_ids:
        return []

    speakers = sorted({segment.speaker for segment in segments if segment.speaker})
    if not speakers:
        return []

    try:
        registry.require_available("3dspeaker-embedding")
        adapter = registry.get_voiceprint("3dspeaker-embedding")
    except Exception as exc:
        return [
            VoiceprintSpeakerMatch(
                speaker=speaker,
                scope_mode=scope_mode,  # type: ignore[arg-type]
                scope_group_id=group_id,
                candidate_profile_ids=candidate_ids,
                error=str(exc),
            )
            for speaker in speakers
        ]

    matches: list[VoiceprintSpeakerMatch] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="voiceprint-speaker-"))
    try:
        try:
            probe_assets = _build_speaker_probe_assets(asset, segments, speakers, tmpdir)
        except Exception as exc:
            return [
                VoiceprintSpeakerMatch(
                    speaker=speaker,
                    scope_mode=scope_mode,  # type: ignore[arg-type]
                    scope_group_id=group_id,
                    candidate_profile_ids=candidate_ids,
                    error=str(exc),
                )
                for speaker in speakers
            ]

        probe_asset_by_speaker = dict(probe_assets)
        for speaker in speakers:
            probe_asset = probe_asset_by_speaker.get(speaker)
            if probe_asset is None:
                matches.append(
                    VoiceprintSpeakerMatch(
                        speaker=speaker,
                        scope_mode=scope_mode,  # type: ignore[arg-type]
                        scope_group_id=group_id,
                        candidate_profile_ids=candidate_ids,
                        error="未能构建该说话人的声纹探针音频",
                    )
                )
                continue

            try:
                identified = adapter.identify(
                    asset=probe_asset,
                    top_k=min(3, len(candidate_ids)),
                    profile_ids=candidate_ids,
                )
                candidates = [
                    VoiceprintMatchCandidate(
                        profile_id=candidate.profile_id,
                        display_name=display_names.get(
                            candidate.profile_id,
                            candidate.display_name,
                        ),
                        score=candidate.score,
                        rank=candidate.rank,
                    )
                    for candidate in identified.candidates
                ]
                matches.append(
                    VoiceprintSpeakerMatch(
                        speaker=speaker,
                        scope_mode=scope_mode,  # type: ignore[arg-type]
                        scope_group_id=group_id,
                        candidate_profile_ids=candidate_ids,
                        candidates=candidates,
                        matched=identified.matched,
                    )
                )
            except Exception as exc:
                matches.append(
                    VoiceprintSpeakerMatch(
                        speaker=speaker,
                        scope_mode=scope_mode,  # type: ignore[arg-type]
                        scope_group_id=group_id,
                        candidate_profile_ids=candidate_ids,
                        error=str(exc),
                    )
                )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return matches


def _resolve_voiceprint_candidates(
    scope_mode: str,
    group_id: str | None,
    profile_ids: list[str] | None,
) -> tuple[list[str], dict[str, str]]:
    from apps.api.app.services import job_db

    requested_ids = [profile_id for profile_id in (profile_ids or []) if profile_id]
    with job_db.session() as db:
        query = db.query(job_db.VoiceprintProfileRecord).filter(
            job_db.VoiceprintProfileRecord.sample_count > 0
        )
        if requested_ids:
            query = query.filter(job_db.VoiceprintProfileRecord.profile_id.in_(requested_ids))
        elif scope_mode == "group":
            if not group_id:
                return [], {}
            member_ids = [
                item.profile_id
                for item in db.query(job_db.VoiceprintGroupMemberRecord)
                .filter(job_db.VoiceprintGroupMemberRecord.group_id == group_id)
                .all()
            ]
            if not member_ids:
                return [], {}
            query = query.filter(job_db.VoiceprintProfileRecord.profile_id.in_(member_ids))
        elif scope_mode != "all":
            return [], {}

        records = query.order_by(job_db.VoiceprintProfileRecord.created_at.desc()).all()
        ids = [record.profile_id for record in records]
        return ids, {record.profile_id: record.display_name for record in records}


def _build_speaker_probe_assets(
    asset: AudioAsset,
    segments: list[Segment],
    speakers: list[str],
    tmpdir: Path,
    *,
    max_probe_seconds: float = 60.0,
    min_segment_ms: int = 1200,
    min_confidence: float = 0.35,
    max_overlap_ratio: float = 0.2,
) -> list[tuple[str, AudioAsset]]:
    import numpy as np
    import soundfile as sf

    audio, sample_rate = sf.read(asset.path, dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)

    built: list[tuple[str, AudioAsset]] = []
    max_samples = int(max_probe_seconds * sample_rate)
    speaker_candidates = _speaker_probe_candidates(
        audio=audio,
        sample_rate=sample_rate,
        segments=segments,
        min_segment_ms=min_segment_ms,
        min_confidence=min_confidence,
        max_overlap_ratio=max_overlap_ratio,
    )
    for speaker in speakers:
        candidates = speaker_candidates.get(speaker, [])
        chunks = []
        total_samples = 0
        for candidate in candidates:
            chunk = candidate["chunk"]
            remaining = max_samples - total_samples
            if remaining <= 0:
                break
            chunks.append(chunk[:remaining])
            total_samples += min(len(chunk), remaining)
        if total_samples <= 0 or not chunks:
            continue
        target = tmpdir / f"{speaker}.wav"
        sf.write(target, np.concatenate(chunks), sample_rate)
        built.append((speaker, AudioAsset(path=str(target), sample_rate=sample_rate, channels=1)))
    return built


def _speaker_probe_candidates(
    *,
    audio,
    sample_rate: int,
    segments: list[Segment],
    min_segment_ms: int,
    min_confidence: float,
    max_overlap_ratio: float,
) -> dict[str, list[dict]]:
    import numpy as np

    raw_by_speaker: dict[str, list[dict]] = {}
    for segment in segments:
        if not segment.speaker or segment.end_ms <= segment.start_ms:
            continue
        start = max(0, int(segment.start_ms * sample_rate / 1000))
        end = min(len(audio), int(segment.end_ms * sample_rate / 1000))
        if end <= start:
            continue

        chunk = audio[start:end]
        rms = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
        duration_ms = segment.end_ms - segment.start_ms
        overlap_ms = _other_speaker_overlap_ms(segment, segments)
        overlap_ratio = overlap_ms / max(1, duration_ms)
        confidence = 1.0 if segment.confidence is None else float(segment.confidence)
        raw_by_speaker.setdefault(segment.speaker, []).append(
            {
                "segment": segment,
                "chunk": chunk,
                "duration_ms": duration_ms,
                "rms": rms,
                "overlap_ratio": overlap_ratio,
                "confidence": confidence,
            }
        )

    selected: dict[str, list[dict]] = {}
    for speaker, candidates in raw_by_speaker.items():
        max_rms = max((item["rms"] for item in candidates), default=0.0)
        energy_floor = max(1e-5, max_rms * 0.08)
        good = [
            item
            for item in candidates
            if item["duration_ms"] >= min_segment_ms
            and item["confidence"] >= min_confidence
            and item["overlap_ratio"] <= max_overlap_ratio
            and item["rms"] >= energy_floor
        ]
        usable = good or [
            item
            for item in candidates
            if item["duration_ms"] >= 500 and item["rms"] >= max(1e-5, max_rms * 0.02)
        ]
        selected[speaker] = sorted(
            usable,
            key=lambda item: (
                -item["confidence"],
                item["overlap_ratio"],
                -item["rms"],
                -item["duration_ms"],
                item["segment"].start_ms,
            ),
        )
    return selected


def _other_speaker_overlap_ms(target: Segment, segments: list[Segment]) -> int:
    overlap = 0
    for segment in segments:
        if not segment.speaker or segment.speaker == target.speaker:
            continue
        start = max(target.start_ms, segment.start_ms)
        end = min(target.end_ms, segment.end_ms)
        if end > start:
            overlap += end - start
    return overlap


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
    voiceprint_scope_mode: str = "none",
    voiceprint_group_id: str | None = None,
    voiceprint_profile_ids: list[str] | None = None,
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
            voiceprint_scope_mode=voiceprint_scope_mode,
            voiceprint_group_id=voiceprint_group_id,
            voiceprint_profile_ids=voiceprint_profile_ids,
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
    voiceprint_scope_mode: str = "none",
    voiceprint_group_id: str | None = None,
    voiceprint_profile_ids: list[str] | None = None,
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
                        "voiceprint_scope_mode": voiceprint_scope_mode,
                        "voiceprint_group_id": voiceprint_group_id,
                        "voiceprint_profile_ids": voiceprint_profile_ids,
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
        voiceprint_scope_mode=voiceprint_scope_mode,
        voiceprint_group_id=voiceprint_group_id,
        voiceprint_profile_ids=voiceprint_profile_ids,
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
