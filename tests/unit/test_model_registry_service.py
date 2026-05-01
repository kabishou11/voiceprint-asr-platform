from __future__ import annotations

from model_adapters import ModelRegistry

from apps.api.app.services import model_registry as model_registry_module
from apps.api.app.services.model_registry import ModelRegistryService, ModelRuntimeStatus


class _LoadableAdapter:
    key = "loadable"
    display_name = "Loadable"
    provider = "unit"
    experimental = False

    def __init__(self) -> None:
        self._model = None

    def _load_model(self):
        self._model = object()
        return self._model


class _NoRuntimeAdapter:
    key = "no-runtime"
    display_name = "No Runtime"
    provider = "unit"
    experimental = False

    def _ensure_backend(self) -> bool:
        return True


def _registry_with(adapter: object, key: str = "unit-model") -> ModelRegistry:
    registry = ModelRegistry()
    registry.register(
        key,
        "transcription",
        adapter,
        provider="unit",
        display_name="Unit Model",
        availability="available",
    )
    return registry


def test_load_model_does_not_mark_backend_only_adapter_as_loaded(monkeypatch) -> None:
    monkeypatch.setattr(
        model_registry_module,
        "get_model_registry",
        lambda: _registry_with(_NoRuntimeAdapter()),
    )

    service = ModelRegistryService()
    result = service.load_model("unit-model")

    assert result.status.value == ModelRuntimeStatus.load_failed.value
    assert "未暴露可加载" in (result.error or "")


def test_unload_model_returns_released_memory_and_clears_adapter(monkeypatch) -> None:
    adapter = _LoadableAdapter()
    monkeypatch.setattr(
        model_registry_module,
        "get_model_registry",
        lambda: _registry_with(adapter),
    )

    service = ModelRegistryService()
    runtime = service._get_runtime("unit-model")
    runtime.status = ModelRuntimeStatus.loaded
    runtime.gpu_memory_mb = 321
    adapter._model = object()

    result = service.unload_model("unit-model")

    assert result.gpu_memory_mb == 321
    assert adapter._model is None
    assert service._get_runtime("unit-model").status == ModelRuntimeStatus.unloaded
