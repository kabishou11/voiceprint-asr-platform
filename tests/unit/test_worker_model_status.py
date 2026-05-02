from __future__ import annotations

from types import SimpleNamespace

from apps.api.app.services import worker_model_status as worker_status_module
from apps.api.app.services.worker_model_status import get_worker_model_status, warmup_worker_model
from apps.worker.app import worker_runtime


class _FakeRegistry:
    def __init__(self, adapter=None):
        self.adapter = adapter or _LoadableAdapter()
        self._entries = {
            "funasr-nano": SimpleNamespace(
                key="funasr-nano",
                display_name="FunASR Nano",
                task="transcription",
                provider="funasr",
                availability="available",
                experimental=False,
                adapter=self.adapter,
            )
        }

    def list_entries(self):
        return list(self._entries.values()) + [
            SimpleNamespace(
                key="3dspeaker-diarization",
                display_name="3D-Speaker Diarization",
                task="diarization",
                provider="3dspeaker",
                availability="available",
                experimental=False,
                adapter=_LoadableAdapter(),
            ),
        ]

    def require_available(self, key):
        entry = self._entries.get(key)
        if entry is None:
            raise ValueError(f"模型 '{key}' 未注册")
        if entry.availability != "available":
            raise RuntimeError("模型不可用")


class _LoadableAdapter:
    def __init__(self) -> None:
        self._model = None

    def _load_model(self):
        self._model = object()
        return self._model


class _BackendOnlyAdapter:
    def _ensure_backend(self):
        return True


class _FakeAsyncResult:
    def __init__(self, payload):
        self.payload = payload

    def get(self, timeout):
        assert timeout == 2.5
        return self.payload


class _FakeCelery:
    def __init__(self, payload):
        self.payload = payload
        self.task_name = None

    def send_task(self, task_name):
        self.task_name = task_name
        return _FakeAsyncResult(self.payload)

    def send_task_with_args(self, task_name, args=None):
        self.task_name = task_name
        self.args = args
        return _FakeAsyncResult(self.payload)


def test_describe_worker_model_status_reports_registry_and_gpu(monkeypatch) -> None:
    monkeypatch.setattr(worker_runtime, "get_worker_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(worker_runtime, "_worker_gpu_info", lambda: {"cuda_available": False})

    payload = worker_runtime.describe_worker_model_status()

    assert payload["hostname"]
    assert payload["gpu"] == {"cuda_available": False}
    assert [item["key"] for item in payload["items"]] == [
        "funasr-nano",
        "3dspeaker-diarization",
    ]
    assert payload["items"][0]["runtime_status"] == "unloaded"
    assert payload["items"][0]["loaded"] is False


def test_describe_worker_model_status_reports_loaded_runtime(monkeypatch) -> None:
    adapter = _LoadableAdapter()
    adapter._load_model()
    monkeypatch.setattr(worker_runtime, "get_worker_registry", lambda: _FakeRegistry(adapter))
    monkeypatch.setattr(worker_runtime, "_cuda_memory_mb", lambda: 1234)

    payload = worker_runtime.describe_worker_model_status()

    first = payload["items"][0]
    assert first["runtime_status"] == "loaded"
    assert first["loaded"] is True
    assert first["gpu_memory_mb"] == 1234


def test_warmup_worker_model_loads_runtime_in_worker_process(monkeypatch) -> None:
    adapter = _LoadableAdapter()
    monkeypatch.setattr(worker_runtime, "get_worker_registry", lambda: _FakeRegistry(adapter))
    monkeypatch.setattr(worker_runtime, "_worker_gpu_info", lambda: {"cuda_available": True})

    payload = worker_runtime.warmup_worker_model("funasr-nano")

    assert payload["status"] == "loaded"
    assert payload["key"] == "funasr-nano"
    assert payload["error"] is None
    assert adapter._model is not None


def test_warmup_worker_model_rejects_backend_only_adapter(monkeypatch) -> None:
    monkeypatch.setattr(
        worker_runtime,
        "get_worker_registry",
        lambda: _FakeRegistry(_BackendOnlyAdapter()),
    )

    payload = worker_runtime.warmup_worker_model("funasr-nano")

    assert payload["status"] == "load_failed"
    assert "未暴露可加载" in payload["error"]


def test_get_worker_model_status_reports_offline_worker(monkeypatch) -> None:
    monkeypatch.setattr(worker_status_module, "worker_available", lambda refresh=True: False)
    monkeypatch.setattr(worker_status_module, "worker_error", lambda: "worker_offline")

    status = get_worker_model_status()

    assert status.online is False
    assert status.error == "worker_offline"
    assert status.items == []


def test_get_worker_model_status_reads_sampled_worker_payload(monkeypatch) -> None:
    payload = {
        "hostname": "worker-1",
        "gpu": {
            "name": "NVIDIA",
            "total_memory_mb": 8192,
            "used_memory_mb": 1024,
            "cuda_available": True,
        },
        "items": [
            {
                "key": "funasr-nano",
                "display_name": "FunASR Nano",
                "task": "transcription",
                "provider": "funasr",
                "availability": "available",
                "runtime_status": "loaded",
                "loaded": True,
                "gpu_memory_mb": 1024,
                "error": None,
                "experimental": False,
            }
        ],
    }
    fake_celery = _FakeCelery(payload)
    monkeypatch.setattr(worker_status_module, "worker_available", lambda refresh=True: True)
    monkeypatch.setattr(worker_status_module, "get_celery_app", lambda: fake_celery)

    status = get_worker_model_status(timeout_seconds=2.5)

    assert status.online is True
    assert status.hostname == "worker-1"
    assert status.gpu is not None
    assert status.gpu.cuda_available is True
    assert [item.key for item in status.items] == ["funasr-nano"]
    assert status.items[0].runtime_status.value == "loaded"
    assert status.items[0].loaded is True
    assert status.items[0].gpu_memory_mb == 1024
    assert fake_celery.task_name == worker_status_module.MODEL_STATUS_TASK_NAME


def test_warmup_worker_model_reports_offline_worker(monkeypatch) -> None:
    monkeypatch.setattr(worker_status_module, "worker_available", lambda refresh=True: False)
    monkeypatch.setattr(worker_status_module, "worker_error", lambda: "worker_offline")

    status = warmup_worker_model("funasr-nano")

    assert status.online is False
    assert status.status == "load_failed"
    assert status.key == "funasr-nano"
    assert status.error == "worker_offline"


def test_warmup_worker_model_reads_worker_payload(monkeypatch) -> None:
    payload = {
        "key": "funasr-nano",
        "status": "loaded",
        "hostname": "worker-1",
        "gpu": {
            "name": "NVIDIA",
            "total_memory_mb": 8192,
            "used_memory_mb": 2048,
            "cuda_available": True,
        },
        "error": None,
    }
    fake_celery = _FakeCelery(payload)
    monkeypatch.setattr(worker_status_module, "worker_available", lambda refresh=True: True)
    monkeypatch.setattr(worker_status_module, "get_celery_app", lambda: fake_celery)
    monkeypatch.setattr(fake_celery, "send_task", fake_celery.send_task_with_args)

    status = warmup_worker_model("funasr-nano", timeout_seconds=2.5)

    assert status.online is True
    assert status.status == "loaded"
    assert status.hostname == "worker-1"
    assert fake_celery.task_name == worker_status_module.MODEL_WARMUP_TASK_NAME
    assert fake_celery.args == ["funasr-nano"]
