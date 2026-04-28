"""声纹任务 - Celery Task 封装。

提供异步声纹任务的注册和执行函数。
"""
from __future__ import annotations

import logging

from domain.schemas.voiceprint import VoiceprintIdentificationResult, VoiceprintVerificationResult
from model_adapters import resolve_audio_asset_path

from ..celery_app import get_celery_app, is_async_available
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry
from ._base import update_job_result, update_job_status

logger = logging.getLogger(__name__)


def _enroll_voiceprint_sync(
    job_id: str,
    asset_name: str,
    profile_id: str,
    model_key: str = "3dspeaker-embedding",
    mode: str = "replace",
) -> dict:
    """同步执行声纹注册任务（内部实现）。"""
    from apps.api.app.services.voiceprint_service import voiceprint_service

    _, enrollment = voiceprint_service.enroll_profile(
        profile_id=profile_id,
        asset_name=asset_name,
        mode=mode,
        source_job_id=job_id,
    )
    return enrollment


def _verify_voiceprint_sync(
    job_id: str,
    asset_name: str,
    profile_id: str,
    threshold: float,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintVerificationResult:
    """同步执行声纹验证任务（内部实现）。"""
    registry = get_worker_registry()
    registry.require_available(model_key)
    adapter = registry.get_voiceprint(model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))
    return adapter.verify(asset=asset, profile_id=profile_id, threshold=threshold)


def _identify_voiceprint_sync(
    job_id: str,
    asset_name: str,
    top_k: int,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintIdentificationResult:
    """同步执行声纹识别任务（内部实现）。"""
    registry = get_worker_registry()
    registry.require_available(model_key)
    adapter = registry.get_voiceprint(model_key)
    asset = preprocess_audio(_adapter_asset(asset_name))
    return adapter.identify(asset=asset, top_k=top_k)


def _adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))


# ============ Task 执行函数（Worker 入口） ============


def execute_enroll_voiceprint_task(
    job_id: str,
    asset_name: str,
    profile_id: str,
    model_key: str = "3dspeaker-embedding",
    mode: str = "replace",
) -> dict:
    """执行声纹注册任务（Celery Worker 入口）。"""
    update_job_status(job_id, "running")

    try:
        result = _enroll_voiceprint_sync(
            job_id=job_id,
            asset_name=asset_name,
            profile_id=profile_id,
            model_key=model_key,
            mode=mode,
        )
        update_job_result(job_id, result=result, status="succeeded")
        return result
    except Exception as e:
        logger.error(f"声纹注册任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


def execute_verify_voiceprint_task(
    job_id: str,
    asset_name: str,
    profile_id: str,
    threshold: float,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintVerificationResult:
    """执行声纹验证任务（Celery Worker 入口）。"""
    update_job_status(job_id, "running")

    try:
        result = _verify_voiceprint_sync(
            job_id=job_id,
            asset_name=asset_name,
            profile_id=profile_id,
            threshold=threshold,
            model_key=model_key,
        )
        update_job_result(job_id, result=result.model_dump(), status="succeeded")
        return result
    except Exception as e:
        logger.error(f"声纹验证任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


def execute_identify_voiceprint_task(
    job_id: str,
    asset_name: str,
    top_k: int,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintIdentificationResult:
    """执行声纹识别任务（Celery Worker 入口）。"""
    update_job_status(job_id, "running")

    try:
        result = _identify_voiceprint_sync(
            job_id=job_id,
            asset_name=asset_name,
            top_k=top_k,
            model_key=model_key,
        )
        update_job_result(job_id, result=result.model_dump(), status="succeeded")
        return result
    except Exception as e:
        logger.error(f"声纹识别任务 {job_id} 执行失败: {e}")
        update_job_result(job_id, status="failed", error_message=str(e))
        raise


# ============ Celery Task 注册 ============

_celery_app = None
_enroll_task = None
_verify_task = None
_identify_task = None


def _init_celery_tasks():
    global _celery_app, _enroll_task, _verify_task, _identify_task

    if _enroll_task is not None:
        return

    try:
        celery = get_celery_app()
        if celery is not None:
            _enroll_task = celery.task(
                execute_enroll_voiceprint_task,
                name="apps.worker.app.tasks.voiceprint.execute_enroll_voiceprint_task",
            )
            _verify_task = celery.task(
                execute_verify_voiceprint_task,
                name="apps.worker.app.tasks.voiceprint.execute_verify_voiceprint_task",
            )
            _identify_task = celery.task(
                execute_identify_voiceprint_task,
                name="apps.worker.app.tasks.voiceprint.execute_identify_voiceprint_task",
            )
            logger.info("Celery 声纹任务已注册")
    except Exception as e:
        logger.warning(f"注册 Celery 声纹任务失败: {e}")


def _get_task_or_wrapper(func, task_var):
    """获取 task 或兼容 wrapper。"""
    global locals
    if task_var is None:
        _init_celery_tasks()
    if task_var is not None:
        return task_var

    def noop_task(*args, **kwargs):
        return func(*args, **kwargs)

    return noop_task


enroll_voiceprint_task = None
verify_voiceprint_task = None
identify_voiceprint_task = None


def _init_wrapper():
    global enroll_voiceprint_task, verify_voiceprint_task, identify_voiceprint_task

    if enroll_voiceprint_task is not None:
        return

    _init_celery_tasks()

    # 如果没有 Celery，返回兼容 wrapper
    enroll_voiceprint_task = _enroll_task if _enroll_task else lambda *args, **kwargs: execute_enroll_voiceprint_task(*args, **kwargs)
    verify_voiceprint_task = _verify_task if _verify_task else lambda *args, **kwargs: execute_verify_voiceprint_task(*args, **kwargs)
    identify_voiceprint_task = _identify_task if _identify_task else lambda *args, **kwargs: execute_identify_voiceprint_task(*args, **kwargs)


# ============ 公开 API ============


def enroll_voiceprint(
    job_id: str,
    asset_name: str,
    profile_id: str,
    model_key: str = "3dspeaker-embedding",
    mode: str = "replace",
) -> dict:
    """执行声纹注册任务。

    Args:
        job_id: 任务 ID
        asset_name: 音频资产名
        profile_id: 声纹档案 ID
        model_key: 模型键

    Returns:
        注册结果
    """
    _init_wrapper()

    if is_async_available() and _enroll_task is not None:
        _enroll_task.apply_async(args=[job_id, asset_name, profile_id, model_key, mode])
        logger.info(f"声纹注册任务 {job_id} 已提交到队列")
        return {
            "profile_id": profile_id,
            "asset_name": asset_name,
            "status": "queued",
            "mode": mode,
        }

    logger.info(f"声纹注册任务 {job_id} 同步执行")
    return _enroll_voiceprint_sync(
        job_id=job_id,
        asset_name=asset_name,
        profile_id=profile_id,
        model_key=model_key,
        mode=mode,
    )


def verify_voiceprint(
    job_id: str,
    asset_name: str,
    profile_id: str,
    threshold: float,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintVerificationResult:
    """执行声纹验证任务。

    Args:
        job_id: 任务 ID
        asset_name: 音频资产名
        profile_id: 声纹档案 ID
        threshold: 验证阈值
        model_key: 模型键

    Returns:
        验证结果
    """
    _init_wrapper()

    if is_async_available() and _verify_task is not None:
        _verify_task.apply_async(args=[job_id, asset_name, profile_id, threshold, model_key])
        logger.info(f"声纹验证任务 {job_id} 已提交到队列")
        return VoiceprintVerificationResult(
            profile_id=profile_id,
            score=0.0,
            threshold=threshold,
            matched=False,
        )

    logger.info(f"声纹验证任务 {job_id} 同步执行")
    return _verify_voiceprint_sync(
        job_id=job_id, asset_name=asset_name, profile_id=profile_id, threshold=threshold, model_key=model_key
    )


def identify_voiceprint(
    job_id: str,
    asset_name: str,
    top_k: int,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintIdentificationResult:
    """执行声纹识别任务。

    Args:
        job_id: 任务 ID
        asset_name: 音频资产名
        top_k: 返回 top-k 结果
        model_key: 模型键

    Returns:
        识别结果
    """
    _init_wrapper()

    if is_async_available() and _identify_task is not None:
        _identify_task.apply_async(args=[job_id, asset_name, top_k, model_key])
        logger.info(f"声纹识别任务 {job_id} 已提交到队列")
        return VoiceprintIdentificationResult(candidates=[], matched=False)

    logger.info(f"声纹识别任务 {job_id} 同步执行")
    return _identify_voiceprint_sync(job_id=job_id, asset_name=asset_name, top_k=top_k, model_key=model_key)
