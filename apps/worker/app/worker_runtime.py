from __future__ import annotations

from functools import lru_cache

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
