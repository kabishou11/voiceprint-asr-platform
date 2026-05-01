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
from ...services.meeting_minutes_config import get_meeting_minutes_llm_info
from ...services.model_registry import ModelRegistryService
from ...services.worker_model_status import get_worker_model_status, warmup_worker_model
from ..schemas import (
    HealthResponse,
    ModelListWithGPUResponse,
    ModelLoadResponse,
    ModelUnloadResponse,
    WorkerModelWarmupResponse,
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
        meeting_minutes_llm=get_meeting_minutes_llm_info(settings),
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
    return ModelListWithGPUResponse(
        items=items,
        gpu=gpu,
        audio_decoder=get_audio_decoder_info(),
        worker_model_status=get_worker_model_status(),
    )


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


@router.post(
    "/models/{model_key}/warmup-worker",
    response_model=WorkerModelWarmupResponse,
    summary="预热 Worker 进程模型",
    description=(
        "通过 Celery 在 Worker 进程中加载指定模型，"
        "用于确认真实任务执行进程已准备好模型和 CUDA。"
    ),
)
def warmup_worker_model_route(model_key: str):
    result = warmup_worker_model(model_key)
    if result.online is False:
        raise HTTPException(status_code=409, detail=result.error or "Worker 不可用")
    if result.status == "load_failed":
        raise HTTPException(status_code=409, detail=result.error or "Worker 模型预热失败")
    return result


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
