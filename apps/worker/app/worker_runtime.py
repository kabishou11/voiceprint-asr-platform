from __future__ import annotations

from apps.api.app.core.config import get_settings
from model_adapters import ModelRegistry, build_default_registry


def get_worker_registry() -> ModelRegistry:
    settings = get_settings()
    return build_default_registry(
        funasr_model=settings.funasr_model,
        three_d_speaker_model=settings.three_d_speaker_model,
        pyannote_model=settings.pyannote_model,
        enable_pyannote=settings.enable_pyannote,
    )


class WorkerRuntime:
    def __init__(self) -> None:
        self.registry = get_worker_registry()

    def describe_capabilities(self) -> list[str]:
        return [f"{entry.task}:{entry.key}:{entry.availability}" for entry in self.registry.list_entries()]


def get_worker() -> WorkerRuntime:
    return WorkerRuntime()
