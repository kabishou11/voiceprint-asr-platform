from __future__ import annotations

import socket
from functools import lru_cache
from typing import Any

from model_adapters import ModelRegistry, build_default_registry

from apps.api.app.core.config import get_settings


@lru_cache(maxsize=1)
def get_worker_registry() -> ModelRegistry:
    settings = get_settings()
    return build_default_registry(
        funasr_model=settings.funasr_model,
        three_d_speaker_model=settings.three_d_speaker_model,
        pyannote_model=settings.pyannote_model,
        enable_pyannote=settings.enable_pyannote,
        enable_3d_speaker_adaptive_clustering=settings.enable_3d_speaker_adaptive_clustering,
    )


def reset_worker_registry() -> None:
    get_worker_registry.cache_clear()


def _worker_gpu_info() -> dict[str, Any]:
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            total = int(props.total_memory / 1024 / 1024)
            used = int(torch.cuda.memory_allocated() / 1024 / 1024)
            return {
                "name": props.name,
                "total_memory_mb": total,
                "used_memory_mb": used,
                "cuda_available": True,
            }
    except Exception:
        pass
    return {
        "name": None,
        "total_memory_mb": None,
        "used_memory_mb": None,
        "cuda_available": False,
    }


def _runtime_loaded(adapter: object) -> bool:
    return any(
        getattr(adapter, attr, None) is not None
        for attr in (
            "_model",
            "_vad_runtime_model",
            "_pipeline",
            "_campplus_model",
            "_feature_extractor",
            "_sv_model",
        )
    )


def _cuda_memory_mb() -> int | None:
    try:
        import torch

        if torch.cuda.is_available():
            mem_info = torch.cuda.mem_get_info()
            if len(mem_info) >= 2:
                return int((mem_info[1] - mem_info[0]) / 1024 / 1024)
            return int(torch.cuda.memory_allocated() / 1024 / 1024)
    except Exception:
        pass
    return None


def _adapter_runtime_status(entry) -> dict[str, Any]:
    loaded = _runtime_loaded(entry.adapter)
    if loaded:
        runtime_status = "loaded"
    elif entry.availability == "unavailable":
        runtime_status = "load_failed"
    else:
        runtime_status = "unloaded"

    error = None
    if entry.availability == "unavailable":
        error = "模型不可用：请检查本地模型文件、运行时依赖和 CUDA。"

    return {
        "runtime_status": runtime_status,
        "loaded": loaded,
        "gpu_memory_mb": _cuda_memory_mb() if loaded else None,
        "error": error,
    }


def _load_adapter_runtime(adapter: object) -> bool:
    loaded = False
    if hasattr(adapter, "_load_model"):
        result = adapter._load_model()
        loaded = result is not None or _runtime_loaded(adapter)
    if not loaded and hasattr(adapter, "_load_pipeline"):
        result = adapter._load_pipeline()
        loaded = result is not None or _runtime_loaded(adapter)
    if not loaded and hasattr(adapter, "_ensure_backend"):
        loaded = bool(adapter._ensure_backend()) and _runtime_loaded(adapter)
    return loaded


def describe_worker_model_status() -> dict[str, Any]:
    registry = get_worker_registry()
    return {
        "hostname": socket.gethostname(),
        "gpu": _worker_gpu_info(),
        "items": [
            {
                "key": entry.key,
                "display_name": entry.display_name,
                "task": entry.task,
                "provider": entry.provider,
                "availability": entry.availability,
                "experimental": entry.experimental,
                **_adapter_runtime_status(entry),
            }
            for entry in registry.list_entries()
        ],
    }


def warmup_worker_model(model_key: str) -> dict[str, Any]:
    registry = get_worker_registry()
    entry = registry._entries.get(model_key)
    if entry is None:
        return {
            "key": model_key,
            "status": "load_failed",
            "hostname": socket.gethostname(),
            "gpu": _worker_gpu_info(),
            "error": f"模型 '{model_key}' 未注册",
        }

    try:
        registry.require_available(model_key)
        loaded = _load_adapter_runtime(entry.adapter)
        if not loaded:
            return {
                "key": model_key,
                "status": "load_failed",
                "hostname": socket.gethostname(),
                "gpu": _worker_gpu_info(),
                "error": "模型未暴露可加载的真实推理对象，未标记为已加载。",
            }
        return {
            "key": model_key,
            "status": "loaded",
            "hostname": socket.gethostname(),
            "gpu": _worker_gpu_info(),
            "error": None,
        }
    except Exception as exc:
        return {
            "key": model_key,
            "status": "load_failed",
            "hostname": socket.gethostname(),
            "gpu": _worker_gpu_info(),
            "error": str(exc),
        }


class WorkerRuntime:
    def __init__(self) -> None:
        self.registry = get_worker_registry()

    def describe_capabilities(self) -> list[str]:
        return [
            f"{entry.task}:{entry.key}:{entry.availability}"
            for entry in self.registry.list_entries()
        ]


def get_worker() -> WorkerRuntime:
    return WorkerRuntime()
