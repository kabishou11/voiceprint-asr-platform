from __future__ import annotations

from dataclasses import dataclass

from ..api.schemas import ModelInfo
from .model_runtime import get_model_registry


@dataclass(slots=True)
class RegistryRecord:
    key: str
    display_name: str
    task: str
    provider: str
    availability: str
    experimental: bool = False


class ModelRegistryService:
    def list_models(self) -> list[ModelInfo]:
        registry = get_model_registry()
        return [
            ModelInfo(
                key=entry.key,
                display_name=entry.display_name,
                task=entry.task,
                provider=entry.provider,
                availability=entry.availability,
                experimental=entry.experimental,
            )
            for entry in registry.list_entries()
        ]
