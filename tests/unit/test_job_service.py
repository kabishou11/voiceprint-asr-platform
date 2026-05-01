from domain.schemas.transcript import Segment, TranscriptResult

from apps.api.app.services import job_service as job_service_module
from apps.api.app.services.job_service import JobService, explain_job_status


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
