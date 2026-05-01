from __future__ import annotations

import logging

from ..celery_app import get_celery_app
from ..worker_runtime import describe_worker_model_status, warmup_worker_model

logger = logging.getLogger(__name__)

MODEL_STATUS_TASK_NAME = "apps.worker.app.tasks.model_status.describe_worker_model_status_task"
MODEL_WARMUP_TASK_NAME = "apps.worker.app.tasks.model_status.warmup_worker_model_task"


def describe_worker_model_status_task() -> dict:
    return describe_worker_model_status()


def warmup_worker_model_task(model_key: str) -> dict:
    return warmup_worker_model(model_key)


_model_status_task = None
_model_warmup_task = None


def get_model_status_task():
    global _model_status_task
    if _model_status_task is not None:
        return _model_status_task

    try:
        celery = get_celery_app()
        if celery is not None:
            _model_status_task = celery.task(
                describe_worker_model_status_task,
                name=MODEL_STATUS_TASK_NAME,
            )
            logger.info("Celery Worker 模型状态探针已注册")
    except Exception as exc:
        logger.warning(f"注册 Worker 模型状态探针失败: {exc}")
    return _model_status_task


def get_model_warmup_task():
    global _model_warmup_task
    if _model_warmup_task is not None:
        return _model_warmup_task

    try:
        celery = get_celery_app()
        if celery is not None:
            _model_warmup_task = celery.task(
                warmup_worker_model_task,
                name=MODEL_WARMUP_TASK_NAME,
            )
            logger.info("Celery Worker 模型预热任务已注册")
    except Exception as exc:
        logger.warning(f"注册 Worker 模型预热任务失败: {exc}")
    return _model_warmup_task


model_status_task = get_model_status_task()
model_warmup_task = get_model_warmup_task()
