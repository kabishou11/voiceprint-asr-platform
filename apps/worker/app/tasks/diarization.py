"""独立说话人分离任务 - Celery Task 封装。

仅执行 diarization，输出 speaker 时间线，不依赖 ASR 文本。
"""
from __future__ import annotations

import logging

from domain.schemas.transcript import Segment, TranscriptMetadata, TranscriptResult, TranscriptTimeline
from model_adapters import resolve_audio_asset_path

from ..celery_app import get_celery_app, is_async_available
from ..pipelines.alignment import build_exclusive_speaker_timeline
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry
from ._base import update_job_result, update_job_status

logger = logging.getLogger(__name__)


def _run_diarization_sync(
    job_id: str,
    asset_name: str,
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    registry = get_worker_registry()
    registry.require_available(diarization_model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))

    diarization_adapter = registry.get_diarization(diarization_model_key)
    if hasattr(diarization_adapter, "num_speakers"):
        diarization_adapter.num_speakers = num_speakers
    if hasattr(diarization_adapter, "min_speakers"):
        diarization_adapter.min_speakers = min_speakers
    if hasattr(diarization_adapter, "max_speakers"):
        diarization_adapter.max_speakers = max_speakers

    diarization_segments = diarization_adapter.diarize(asset)
    exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)

    segments = exclusive_segments or diarization_segments
    total_text = f"说话人分离完成，共 {len(segments)} 个片段"

    metadata = TranscriptMetadata(
        diarization_model=diarization_model_key,
        alignment_source="exclusive" if exclusive_segments else "regular",
        timelines=[
            TranscriptTimeline(label="Regular diarization", source="regular", segments=diarization_segments),
            TranscriptTimeline(
                label="Exclusive timeline",
                source="exclusive",
                segments=exclusive_segments or diarization_segments,
            ),
        ],
    )

    return TranscriptResult(
        text=total_text,
        language=None,
        segments=segments,
        metadata=metadata,
    )


def _adapter_asset(asset_name: str):
    from model_adapters import AudioAsset
    return AudioAsset(path=resolve_audio_asset_path(asset_name))


def execute_diarization_task(
    job_id: str,
    asset_name: str,
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    update_job_status(job_id, "running")
    try:
        result = _run_diarization_sync(
            job_id=job_id,
            asset_name=asset_name,
            diarization_model_key=diarization_model_key,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        update_job_result(job_id, result=result, status="succeeded")
        return result
    except Exception as e:
        logger.error(f"说话人分离任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


_diarization_task = None


def _init_celery_task():
    global _diarization_task
    if _diarization_task is not None:
        return _diarization_task
    try:
        celery = get_celery_app()
        if celery is not None:
            _diarization_task = celery.task(
                execute_diarization_task,
                name="apps.worker.app.tasks.diarization.execute_diarization_task",
            )
            logger.info("Celery 说话人分离任务已注册")
            return _diarization_task
    except Exception as e:
        logger.warning(f"注册 Celery 说话人分离任务失败: {e}")
    return None


def run_diarization(
    job_id: str,
    asset_name: str,
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    return _run_diarization_sync(
        job_id=job_id,
        asset_name=asset_name,
        diarization_model_key=diarization_model_key,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )


run_diarization_task = None


def get_diarization_task():
    global run_diarization_task
    if run_diarization_task is None:
        task = _init_celery_task()
        run_diarization_task = task if task else execute_diarization_task
    return run_diarization_task
