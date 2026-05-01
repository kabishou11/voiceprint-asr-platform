from __future__ import annotations

from typing import Any

from apps.worker.app.celery_app import get_celery_app, worker_available, worker_error

from ..api.schemas import (
    GPUInfo,
    WorkerModelInfo,
    WorkerModelStatusResponse,
)

MODEL_STATUS_TASK_NAME = "apps.worker.app.tasks.model_status.describe_worker_model_status_task"


def _gpu_from_payload(payload: dict[str, Any] | None) -> GPUInfo | None:
    if not isinstance(payload, dict):
        return None
    return GPUInfo(
        name=payload.get("name"),
        total_memory_mb=payload.get("total_memory_mb"),
        used_memory_mb=payload.get("used_memory_mb"),
        cuda_available=bool(payload.get("cuda_available")),
    )


def _worker_status_from_payload(payload: dict[str, Any]) -> WorkerModelStatusResponse:
    items = [
        WorkerModelInfo(**item)
        for item in payload.get("items", [])
        if isinstance(item, dict)
    ]
    return WorkerModelStatusResponse(
        online=True,
        source="celery_task",
        hostname=payload.get("hostname"),
        items=items,
        gpu=_gpu_from_payload(payload.get("gpu")),
        error=payload.get("error"),
    )


def get_worker_model_status(timeout_seconds: float = 3.0) -> WorkerModelStatusResponse:
    if not worker_available(refresh=True):
        return WorkerModelStatusResponse(
            online=False,
            source="celery_task",
            error=worker_error() or "worker_offline",
        )

    try:
        celery = get_celery_app()
        if celery is None:
            return WorkerModelStatusResponse(
                online=False,
                source="celery_task",
                error="celery_unavailable",
            )
        async_result = celery.send_task(MODEL_STATUS_TASK_NAME)
        payload = async_result.get(timeout=timeout_seconds)
        if not isinstance(payload, dict):
            raise TypeError("Worker 模型状态探针返回值不是 dict")
        return _worker_status_from_payload(payload)
    except Exception as exc:
        return WorkerModelStatusResponse(
            online=False,
            source="celery_task",
            error=str(exc),
        )
