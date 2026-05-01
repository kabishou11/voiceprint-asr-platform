from __future__ import annotations

from types import SimpleNamespace

from apps.api.app.services import worker_model_status as worker_status_module
from apps.api.app.services.worker_model_status import get_worker_model_status
from apps.worker.app import worker_runtime


class _FakeRegistry:
    def list_entries(self):
        return [
            SimpleNamespace(
                key="funasr-nano",
                display_name="FunASR Nano",
                task="transcription",
                provider="funasr",
                availability="available",
                experimental=False,
            ),
            SimpleNamespace(
                key="3dspeaker-diarization",
                display_name="3D-Speaker Diarization",
                task="diarization",
                provider="3dspeaker",
                availability="available",
                experimental=False,
            ),
        ]


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
    assert fake_celery.task_name == worker_status_module.MODEL_STATUS_TASK_NAME
