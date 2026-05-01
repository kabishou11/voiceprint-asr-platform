from __future__ import annotations

import gc
import threading
from dataclasses import dataclass
from enum import Enum

from ..api.schemas import GPUInfo, ModelInfoWithStatus, ModelStatus
from .model_runtime import get_model_registry


class ModelRuntimeStatus(str, Enum):
    unloaded = "unloaded"
    loading = "loading"
    loaded = "loaded"
    load_failed = "load_failed"


@dataclass(slots=True)
class RegistryRecord:
    key: str
    display_name: str
    task: str
    provider: str
    availability: str
    experimental: bool = False


@dataclass
class ModelRuntimeRecord:
    status: ModelRuntimeStatus = ModelRuntimeStatus.unloaded
    gpu_memory_mb: int | None = None
    load_progress: float | None = None
    error: str | None = None


class ModelRegistryService:
    def __init__(self) -> None:
        self._runtime_state: dict[str, ModelRuntimeRecord] = {}
        self._locks: dict[str, threading.Lock] = {}

    def _get_lock(self, key: str) -> threading.Lock:
        if key not in self._locks:
            self._locks[key] = threading.Lock()
        return self._locks[key]

    def _get_runtime(self, key: str) -> ModelRuntimeRecord:
        if key not in self._runtime_state:
            self._runtime_state[key] = ModelRuntimeRecord()
        return self._runtime_state[key]

    def get_gpu_info(self) -> GPUInfo:
        try:
            import torch

            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                total = int(props.total_memory / 1024 / 1024)
                used = int(torch.cuda.memory_allocated() / 1024 / 1024)
                return GPUInfo(
                    name=props.name,
                    total_memory_mb=total,
                    used_memory_mb=used,
                    cuda_available=True,
                )
        except Exception:
            pass
        return GPUInfo(cuda_available=False)

    def list_models(self) -> list[ModelInfoWithStatus]:
        registry = get_model_registry()
        items: list[ModelInfoWithStatus] = []
        for entry in registry.list_entries():
            runtime = self._get_runtime(entry.key)
            status: ModelStatus
            if entry.availability == "unavailable":
                status = ModelStatus.load_failed
            elif entry.availability == "available":
                if runtime.status == ModelRuntimeStatus.loaded:
                    status = ModelStatus.loaded
                elif runtime.status == ModelRuntimeStatus.loading:
                    status = ModelStatus.loading
                elif runtime.status == ModelRuntimeStatus.load_failed:
                    status = ModelStatus.load_failed
                else:
                    status = ModelStatus.unloaded
            else:
                status = ModelStatus.unloaded

            items.append(
                ModelInfoWithStatus(
                    key=entry.key,
                    display_name=entry.display_name,
                    task=entry.task,
                    provider=entry.provider,
                    availability=entry.availability,
                    status=status,
                    gpu_memory_mb=runtime.gpu_memory_mb,
                    load_progress=runtime.load_progress,
                    error=runtime.error,
                    experimental=entry.experimental,
                )
            )
        return items

    def load_model(self, model_key: str) -> ModelInfoWithStatus:
        lock = self._get_lock(model_key)
        with lock:
            return self._load_model_unlocked(model_key)

    def _load_model_unlocked(self, model_key: str) -> ModelInfoWithStatus:
        registry = get_model_registry()
        entry = registry._entries.get(model_key)
        if entry is None:
            raise ValueError(f"模型 '{model_key}' 未注册")

        runtime = self._get_runtime(model_key)
        runtime.status = ModelRuntimeStatus.loading
        runtime.error = None
        runtime.load_progress = 0.0

        try:
            adapter = entry.adapter
            loaded = False

            # Try _load_model first (FunASR)
            if hasattr(adapter, "_load_model"):
                result = adapter._load_model()
                if result is not None:
                    loaded = True

            # Try _load_pipeline (pyannote)
            if not loaded and hasattr(adapter, "_load_pipeline"):
                result = adapter._load_pipeline()
                if result is not None:
                    loaded = True

            # Try triggering eager initialization only as a last resort. A plain
            # _ensure_backend() is not enough to claim a heavy model is loaded,
            # but it is still useful for adapters without a dedicated loader.
            if not loaded and hasattr(adapter, "_ensure_backend"):
                has_heavy_runtime = any(
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
                if adapter._ensure_backend() and has_heavy_runtime:
                    loaded = True

            if loaded:
                runtime.load_progress = 1.0
                runtime.status = ModelRuntimeStatus.loaded
                runtime.gpu_memory_mb = self._get_cuda_memory_mb()
            else:
                runtime.status = ModelRuntimeStatus.load_failed
                runtime.gpu_memory_mb = None
                runtime.error = "模型未暴露可加载的真实推理对象，未标记为已加载。"
        except Exception as exc:
            runtime.status = ModelRuntimeStatus.load_failed
            runtime.error = str(exc)
            runtime.load_progress = None

        return ModelInfoWithStatus(
            key=entry.key,
            display_name=entry.display_name,
            task=entry.task,
            provider=entry.provider,
            availability=entry.availability,
            status=ModelStatus(runtime.status.value),
            gpu_memory_mb=runtime.gpu_memory_mb,
            load_progress=runtime.load_progress,
            error=runtime.error,
            experimental=entry.experimental,
        )

    def unload_model(self, model_key: str) -> ModelInfoWithStatus:
        lock = self._get_lock(model_key)
        with lock:
            return self._unload_model_unlocked(model_key)

    def _unload_model_unlocked(self, model_key: str) -> ModelInfoWithStatus:
        registry = get_model_registry()
        entry = registry._entries.get(model_key)
        if entry is None:
            raise ValueError(f"模型 '{model_key}' 未注册")

        runtime = self._get_runtime(model_key)

        try:
            adapter = entry.adapter

            # Properly release GPU memory: delete objects before freeing CUDA cache
            for attr in (
                "_model",
                "_vad_runtime_model",
                "_pipeline",
                "_vad_model",
                "_campplus_model",
                "_feature_extractor",
                "_cluster_backend",
                "_sv_model",
            ):
                if hasattr(adapter, attr) and getattr(adapter, attr, None) is not None:
                    obj = getattr(adapter, attr)
                    setattr(adapter, attr, None)
                    del obj

            # Run garbage collector to free Python object references
            gc.collect()

            # Now free CUDA cache
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        except Exception:
            pass

        released_mb = runtime.gpu_memory_mb
        runtime.status = ModelRuntimeStatus.unloaded
        runtime.gpu_memory_mb = None
        runtime.load_progress = None
        runtime.error = None

        return ModelInfoWithStatus(
            key=entry.key,
            display_name=entry.display_name,
            task=entry.task,
            provider=entry.provider,
            availability=entry.availability,
            status=ModelStatus.unloaded,
            gpu_memory_mb=released_mb,
            load_progress=None,
            error=None,
            experimental=entry.experimental,
        )

    def _get_cuda_memory_mb(self) -> int | None:
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
