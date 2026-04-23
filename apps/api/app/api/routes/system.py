from fastapi import APIRouter, HTTPException

from ..schemas import (
    HealthResponse,
    GPUInfo,
    ModelInfoWithStatus,
    ModelListWithGPUResponse,
    ModelLoadResponse,
    ModelStatus,
    ModelUnloadResponse,
)
from ...core.config import get_settings
from ...services.model_registry import ModelRegistryService
from apps.worker.app.celery_app import broker_available, is_async_available, worker_available

router = APIRouter(tags=["system"])
registry = ModelRegistryService()


@router.get("/health")
def health():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        broker_available=broker_available(),
        worker_available=worker_available(),
        async_available=is_async_available(),
    )


@router.get("/models")
def list_models():
    items = registry.list_models()
    gpu = registry.get_gpu_info()
    return ModelListWithGPUResponse(items=items, gpu=gpu)


@router.post("/models/{model_key}/load")
def load_model(model_key: str):
    try:
        result = registry.load_model(model_key)
        return ModelLoadResponse(
            key=result.key,
            status=result.status,
            gpu_memory_mb=result.gpu_memory_mb,
            error=result.error,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/models/{model_key}")
def unload_model(model_key: str):
    try:
        result = registry.unload_model(model_key)
        return ModelUnloadResponse(
            key=result.key,
            status=result.status,
            released_mb=result.gpu_memory_mb,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
