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
            }
            for entry in registry.list_entries()
        ],
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
