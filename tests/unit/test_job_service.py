import json
from datetime import datetime, timezone
from uuid import uuid4

from domain.schemas.transcript import Segment, TranscriptResult

from apps.api.app.services import job_db
from apps.api.app.services import job_service as job_service_module
from apps.api.app.services.job_service import JobService, explain_job_status


def _insert_job(
    status: str,
    job_type: str = "transcription",
    request_payload: dict[str, object] | None = None,
) -> str:
    job_id = f"unit-{uuid4().hex}"
    now = datetime.now(timezone.utc)
    with job_db.session() as db:
        db.add(
            job_db.JobRecord(
                job_id=job_id,
                job_type=job_type,
                status=status,
                asset_name="demo.wav",
                request_payload=(
                    json.dumps(request_payload, ensure_ascii=False) if request_payload else None
                ),
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return job_id


def test_sync_transcription_passes_requested_asr_model(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_run_transcription(**kwargs):
        seen["model_key"] = kwargs["model_key"]
        return TranscriptResult(
            text="ok",
            language="zh-cn",
            segments=[Segment(start_ms=0, end_ms=1000, text="ok")],
        )

    service = JobService()
    monkeypatch.setattr(job_service_module, "run_transcription", fake_run_transcription)
    monkeypatch.setattr(service, "_update_job_status", lambda job_id, status: True)
    monkeypatch.setattr(service, "_update_job_result", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "get_job", lambda job_id: None)

    job = service._execute_transcription_sync(
        job_id="job-sync-asr",
        asset_name="demo.wav",
        job_type="transcription",
        asr_model="custom-asr",
    )

    assert seen["model_key"] == "custom-asr"
    assert job.status == "succeeded"


def test_sync_multi_speaker_passes_requested_asr_model(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_run_multi_speaker_transcription(**kwargs):
        seen["asr_model_key"] = kwargs["asr_model_key"]
        return TranscriptResult(
            text="ok",
            language="zh-cn",
            segments=[Segment(start_ms=0, end_ms=1000, text="ok", speaker="SPEAKER_00")],
        )

    service = JobService()
    monkeypatch.setattr(
        job_service_module,
        "run_multi_speaker_transcription",
        fake_run_multi_speaker_transcription,
    )
    monkeypatch.setattr(service, "_update_job_status", lambda job_id, status: True)
    monkeypatch.setattr(service, "_update_job_result", lambda *args, **kwargs: True)
    monkeypatch.setattr(service, "get_job", lambda job_id: None)

    job = service._execute_transcription_sync(
        job_id="job-sync-multi",
        asset_name="demo.wav",
        job_type="multi_speaker_transcription",
        asr_model="custom-asr",
    )

    assert seen["asr_model_key"] == "custom-asr"
    assert job.status == "succeeded"


def test_explain_job_status_reports_worker_outage(monkeypatch) -> None:
    job = job_service_module.JobDetail(
        job_id="job-queued",
        job_type="multi_speaker_transcription",
        status="queued",
        asset_name="demo.wav",
    )

    monkeypatch.setattr(job_service_module, "broker_available", lambda refresh=False: True)
    monkeypatch.setattr(job_service_module, "worker_available", lambda refresh=False: False)
    monkeypatch.setattr(job_service_module, "worker_error", lambda: "no worker heartbeat")

    assert "未检测到在线 Worker" in (explain_job_status(job) or "")
    assert "no worker heartbeat" in (explain_job_status(job) or "")


def test_explain_job_status_classifies_cuda_failure() -> None:
    job = job_service_module.JobDetail(
        job_id="job-failed",
        job_type="transcription",
        status="failed",
        asset_name="demo.wav",
        error_message="CUDA out of memory",
    )

    assert "CUDA/GPU" in (explain_job_status(job) or "")


def test_cancel_job_marks_queued_job_canceled() -> None:
    service = JobService()
    job_id = _insert_job("queued")

    job = service.cancel_job(job_id)

    assert job is not None
    assert job.status == "canceled"
    assert job.error_message == "用户取消任务"
    assert "已取消" in (job.status_explanation or "")


def test_cancel_job_does_not_cancel_terminal_job() -> None:
    service = JobService()
    job_id = _insert_job("succeeded")

    job = service.cancel_job(job_id)

    assert job is not None
    assert job.status == "succeeded"


def test_canceled_job_is_not_overwritten_by_late_worker_result() -> None:
    service = JobService()
    job_id = _insert_job("queued")
    service.cancel_job(job_id)

    updated = service.update_job_result(
        job_id,
        result=TranscriptResult(text="late", language="zh-cn", segments=[]),
        status="succeeded",
    )
    job = service.get_job(job_id)

    assert updated is False
    assert job is not None
    assert job.status == "canceled"
    assert job.result is None


def test_create_transcription_refuses_sync_fallback_when_queue_unavailable(monkeypatch) -> None:
    service = JobService()
    monkeypatch.delenv("ALLOW_SYNC_TRANSCRIPTION_FALLBACK", raising=False)
    monkeypatch.setattr(job_service_module, "is_async_available", lambda refresh=True: False)
    monkeypatch.setattr(job_service_module, "worker_error", lambda: "worker_offline")
    monkeypatch.setattr(job_service_module, "broker_error", lambda: None)
    monkeypatch.setattr(
        service,
        "_execute_transcription_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not sync")),
    )

    try:
        service.create_transcription_job(asset_name="demo.wav")
    except RuntimeError as exc:
        assert "异步任务队列不可用" in str(exc)
        assert "worker_offline" in str(exc)
    else:
        raise AssertionError("queue outage should fail fast")


def test_create_transcription_allows_explicit_sync_fallback(monkeypatch) -> None:
    service = JobService()
    monkeypatch.setenv("ALLOW_SYNC_TRANSCRIPTION_FALLBACK", "1")
    monkeypatch.setattr(job_service_module, "is_async_available", lambda refresh=True: False)

    def fake_execute(**kwargs):
        return job_service_module.JobDetail(
            job_id=kwargs["job_id"],
            job_type=kwargs["job_type"],
            status="succeeded",
            asset_name=kwargs["asset_name"],
            result=TranscriptResult(text="ok", language="zh-cn", segments=[]),
        )

    monkeypatch.setattr(service, "_execute_transcription_sync", fake_execute)

    job = service.create_transcription_job(asset_name="demo.wav")

    assert job.status == "succeeded"


def test_create_transcription_persists_retry_payload(monkeypatch) -> None:
    submitted: dict[str, object] = {}

    class FakeTask:
        def apply_async(self, *args, **kwargs):
            submitted["args"] = args
            submitted["kwargs"] = kwargs

    service = JobService()
    monkeypatch.setattr(job_service_module, "is_async_available", lambda refresh=True: True)
    monkeypatch.setattr(job_service_module, "run_transcription_task", FakeTask())

    job = service.create_transcription_job(
        asset_name="demo.wav",
        asr_model="custom-asr",
        hotwords=["机要", "声纹"],
        language="zh-cn",
        vad_enabled=True,
        itn=False,
    )

    with job_db.session() as db:
        record = db.get(job_db.JobRecord, job.job_id)
        assert record is not None
        payload = json.loads(record.request_payload or "{}")

    assert submitted
    assert payload["asset_name"] == "demo.wav"
    assert payload["asr_model"] == "custom-asr"
    assert payload["hotwords"] == ["机要", "声纹"]
    assert payload["itn"] is False


def test_retry_failed_transcription_creates_new_job_with_original_payload(monkeypatch) -> None:
    submitted: dict[str, object] = {}

    class FakeTask:
        def apply_async(self, *args, **kwargs):
            submitted["args"] = args
            submitted["kwargs"] = kwargs

    payload = {
        "asset_name": "meeting.wav",
        "job_type": "multi_speaker_transcription",
        "asr_model": "custom-asr",
        "diarization_model": "3dspeaker-diarization",
        "hotwords": ["机要"],
        "language": "zh-cn",
        "vad_enabled": True,
        "itn": True,
        "voiceprint_scope_mode": "group",
        "voiceprint_group_id": "group-1",
        "voiceprint_profile_ids": ["profile-1"],
        "num_speakers": 2,
        "min_speakers": 1,
        "max_speakers": 3,
    }
    failed_job_id = _insert_job(
        "failed",
        job_type="multi_speaker_transcription",
        request_payload=payload,
    )

    service = JobService()
    monkeypatch.setattr(job_service_module, "is_async_available", lambda refresh=True: True)
    monkeypatch.setattr(job_service_module, "run_multi_speaker_transcription_task", FakeTask())

    retried = service.retry_job(failed_job_id)

    assert retried is not None
    assert retried.job_id != failed_job_id
    assert retried.status == "queued"
    assert retried.asset_name == "meeting.wav"
    assert submitted["kwargs"]["args"][1] == "meeting.wav"
    kwargs = submitted["kwargs"]["kwargs"]
    assert kwargs["voiceprint_scope_mode"] == "group"
    assert kwargs["voiceprint_group_id"] == "group-1"
    assert kwargs["voiceprint_profile_ids"] == ["profile-1"]
    assert kwargs["num_speakers"] == 2


def test_retry_rejects_running_job() -> None:
    service = JobService()
    job_id = _insert_job(
        "running",
        request_payload={"asset_name": "demo.wav", "job_type": "transcription"},
    )

    try:
        service.retry_job(job_id)
    except job_service_module.JobRetryError as exc:
        assert "仅失败或已取消任务可重试" in str(exc)
    else:
        raise AssertionError("running job should not be retryable")


def test_retry_rejects_legacy_job_without_payload() -> None:
    service = JobService()
    job_id = _insert_job("failed")

    try:
        service.retry_job(job_id)
    except job_service_module.JobRetryError as exc:
        assert "缺少创建参数" in str(exc)
    else:
        raise AssertionError("legacy job without payload should not be retryable")
