from fastapi import APIRouter, HTTPException

from apps.worker.app.celery_app import (
    broker_available,
    broker_error,
    is_async_available,
    worker_available,
    worker_error,
)

from ...core.config import get_settings
from ...services.audio_decoder import get_audio_decoder_info
from ...services.model_registry import ModelRegistryService
from ..schemas import (
    HealthResponse,
    ModelListWithGPUResponse,
    ModelLoadResponse,
    ModelUnloadResponse,
)

router = APIRouter(tags=["系统与模型"])
registry = ModelRegistryService()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="健康检查",
    description="返回服务状态、Celery broker/worker 可用性、当前执行模式（async/sync）。",
)
def health():
    settings = get_settings()
    broker_ready = broker_available(refresh=True)
    worker_ready = worker_available(refresh=True)
    async_ready = broker_ready and worker_ready and is_async_available(refresh=True)
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        audio_decoder=get_audio_decoder_info(),
        broker_available=broker_ready,
        worker_available=worker_ready,
        async_available=async_ready,
        execution_mode="async" if async_ready else "sync",
        broker_error=broker_error(),
        worker_error=worker_error(),
    )


@router.get(
    "/models",
    response_model=ModelListWithGPUResponse,
    summary="获取模型列表与 GPU 状态",
    description="返回所有已注册模型的加载状态，以及当前 GPU 信息（显存、CUDA 可用性）。",
)
def list_models():
    items = registry.list_models()
    gpu = registry.get_gpu_info()
    return ModelListWithGPUResponse(items=items, gpu=gpu, audio_decoder=get_audio_decoder_info())


@router.post(
    "/models/{model_key}/load",
    response_model=ModelLoadResponse,
    summary="加载模型",
    description="将指定模型加载到 GPU/CPU。加载完成后状态变为 loaded。",
)
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/models/{model_key}",
    response_model=ModelUnloadResponse,
    summary="卸载模型",
    description="从 GPU/CPU 卸载指定模型，释放显存。卸载后状态变为 unloaded。",
)
def unload_model(model_key: str):
    try:
        result = registry.unload_model(model_key)
        return ModelUnloadResponse(
            key=result.key,
            status=result.status,
            released_mb=result.gpu_memory_mb,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
