from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
    VoiceprintVerificationResult,
)

from apps.api.app.api.routes import voiceprints as voiceprint_routes
from apps.api.app.services import job_db
from apps.api.app.services import voiceprint_service as voiceprint_module
from apps.api.app.services.voiceprint_service import voiceprint_service
from apps.worker.app.tasks import voiceprint as voiceprint_tasks


class _DummyVoiceprintAdapter:
    def __init__(self) -> None:
        self.enroll_calls: list[tuple[str, str]] = []
        self.identify_profile_ids: list[list[str] | None] = []

    def enroll(self, asset, profile_id: str, mode: str = "replace") -> dict:
        self.enroll_calls.append((profile_id, mode))
        return {
            "profile_id": profile_id,
            "asset": asset.path,
            "status": "enrolled",
            "mode": mode,
        }

    def identify(self, asset, top_k: int, profile_ids: list[str] | None = None):
        self.identify_profile_ids.append(profile_ids)
        candidates = [
            VoiceprintIdentificationCandidate(
                profile_id=(profile_ids or ["profile-a"])[0],
                display_name="候选人",
                score=0.9,
                rank=1,
            )
        ]
        return VoiceprintIdentificationResult(candidates=candidates[:top_k], matched=True)


class _DummyRegistry:
    def __init__(self, adapter: _DummyVoiceprintAdapter) -> None:
        self.adapter = adapter

    def require_available(self, model_key: str) -> None:
        return None

    def get_voiceprint(self, model_key: str) -> _DummyVoiceprintAdapter:
        return self.adapter


class _ApplyAsyncRecorder:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    def apply_async(self, args: list[object]) -> None:
        self.calls.append(args)


def _insert_voiceprint_job(
    job_type: str,
    result: dict | str | None = None,
    status: str = "queued",
    error_message: str | None = None,
) -> str:
    job_id = f"unit-{uuid4().hex}"
    now = datetime.now(timezone.utc)
    stored_result = json.dumps(result) if isinstance(result, dict) else result
    with job_db.session() as db:
        db.add(
            job_db.JobRecord(
                job_id=job_id,
                job_type=job_type,
                status=status,
                asset_name="unit.wav",
                result=stored_result,
                error_message=error_message,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return job_id


def test_voiceprint_enroll_replace_and_append_update_sample_count(monkeypatch) -> None:
    adapter = _DummyVoiceprintAdapter()
    monkeypatch.setattr(voiceprint_module, "get_model_registry", lambda: _DummyRegistry(adapter))
    profile = voiceprint_service.create_profile("单测声纹 replace append", "3dspeaker-embedding")

    updated, first = voiceprint_service.enroll_profile(
        profile.profile_id,
        "声纹-女1.wav",
        mode="replace",
    )
    assert updated.sample_count == 1
    assert first["mode"] == "replace"
    assert first["quality"]["available"] is True
    assert first["quality"]["duration_seconds"] >= 3.0

    updated, second = voiceprint_service.enroll_profile(
        profile.profile_id,
        "5分钟.wav",
        mode="append",
    )
    assert updated.sample_count == 2
    assert second["mode"] == "append"
    assert second["quality"]["warnings"]

    updated, third = voiceprint_service.enroll_profile(
        profile.profile_id,
        "声纹-女1.wav",
        mode="replace",
    )
    assert updated.sample_count == 1
    assert third["mode"] == "replace"
    assert adapter.enroll_calls[-3:] == [
        (profile.profile_id, "replace"),
        (profile.profile_id, "append"),
        (profile.profile_id, "replace"),
    ]


def test_async_voiceprint_enroll_uses_service_metadata_path(monkeypatch) -> None:
    adapter = _DummyVoiceprintAdapter()
    monkeypatch.setattr(voiceprint_module, "get_model_registry", lambda: _DummyRegistry(adapter))
    profile = voiceprint_service.create_profile("单测异步声纹注册", "3dspeaker-embedding")

    result = voiceprint_tasks._enroll_voiceprint_sync(
        job_id="unit-enroll-job",
        asset_name="声纹-女1.wav",
        profile_id=profile.profile_id,
        mode="append",
    )

    updated = voiceprint_service.get_profile(profile.profile_id)
    assert result["mode"] == "append"
    assert updated is not None
    assert updated.sample_count == 1


def test_voiceprint_identify_passes_profile_ids_to_adapter(monkeypatch) -> None:
    adapter = _DummyVoiceprintAdapter()
    monkeypatch.setattr(voiceprint_module, "get_model_registry", lambda: _DummyRegistry(adapter))

    result = voiceprint_service.identify(
        probe_asset_name="5分钟.wav",
        top_k=1,
        profile_ids=["profile-selected"],
    )

    assert result.candidates[0].profile_id == "profile-selected"
    assert adapter.identify_profile_ids == [["profile-selected"]]


def test_async_voiceprint_identify_passes_profile_ids_to_adapter(monkeypatch) -> None:
    adapter = _DummyVoiceprintAdapter()
    monkeypatch.setattr(voiceprint_tasks, "get_worker_registry", lambda: _DummyRegistry(adapter))
    monkeypatch.setattr(voiceprint_tasks, "preprocess_audio", lambda asset: asset)

    result = voiceprint_tasks._identify_voiceprint_sync(
        job_id="unit-identify-job",
        asset_name="5分钟.wav",
        top_k=1,
        profile_ids=["profile-selected"],
    )

    assert result.candidates[0].profile_id == "profile-selected"
    assert adapter.identify_profile_ids == [["profile-selected"]]


def test_async_voiceprint_task_wrappers_return_only_job_receipts(monkeypatch) -> None:
    enroll_task = _ApplyAsyncRecorder()
    verify_task = _ApplyAsyncRecorder()
    identify_task = _ApplyAsyncRecorder()
    monkeypatch.setattr(voiceprint_tasks, "is_async_available", lambda: True)
    monkeypatch.setattr(voiceprint_tasks, "_init_wrapper", lambda: None)
    monkeypatch.setattr(voiceprint_tasks, "_enroll_task", enroll_task)
    monkeypatch.setattr(voiceprint_tasks, "_verify_task", verify_task)
    monkeypatch.setattr(voiceprint_tasks, "_identify_task", identify_task)

    enroll_receipt = voiceprint_tasks.enroll_voiceprint(
        job_id="job-enroll",
        asset_name="声纹-女1.wav",
        profile_id="profile-a",
        mode="append",
    )
    verify_receipt = voiceprint_tasks.verify_voiceprint(
        job_id="job-verify",
        asset_name="5分钟.wav",
        profile_id="profile-a",
        threshold=0.7,
    )
    identify_receipt = voiceprint_tasks.identify_voiceprint(
        job_id="job-identify",
        asset_name="5分钟.wav",
        top_k=2,
        profile_ids=["profile-a"],
    )

    assert enroll_receipt == {"job_id": "job-enroll", "status": "queued"}
    assert verify_receipt == {"job_id": "job-verify", "status": "queued"}
    assert identify_receipt == {"job_id": "job-identify", "status": "queued"}
    assert enroll_task.calls == [
        ["job-enroll", "声纹-女1.wav", "profile-a", "3dspeaker-embedding", "append"]
    ]
    assert verify_task.calls == [
        ["job-verify", "5分钟.wav", "profile-a", 0.7, "3dspeaker-embedding"]
    ]
    assert identify_task.calls == [
        ["job-identify", "5分钟.wav", 2, "3dspeaker-embedding", ["profile-a"]]
    ]


def test_sync_voiceprint_job_writes_success_result_to_job_record() -> None:
    job_id = _insert_voiceprint_job("voiceprint_verify")
    result = VoiceprintVerificationResult(
        profile_id="profile-a",
        score=0.92,
        threshold=0.7,
        matched=True,
    )

    returned = voiceprint_routes._run_sync_voiceprint_job(job_id, lambda: result)

    assert returned is result
    with job_db.session() as db:
        record = db.get(job_db.JobRecord, job_id)
        assert record is not None
        assert record.status == "succeeded"
        assert record.error_message is None
        assert json.loads(record.result or "{}") == result.model_dump()


def test_sync_voiceprint_job_writes_error_to_job_record() -> None:
    job_id = _insert_voiceprint_job("voiceprint_verify")

    def fail() -> None:
        raise ValueError("bad voiceprint")

    try:
        voiceprint_routes._run_sync_voiceprint_job(job_id, fail)
        raise AssertionError("expected HTTPException")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400

    with job_db.session() as db:
        record = db.get(job_db.JobRecord, job_id)
        assert record is not None
        assert record.status == "failed"
        assert record.error_message == "bad voiceprint"
        assert record.result is None


def test_voiceprint_job_endpoint_maps_enroll_verify_identify_results() -> None:
    enroll_result = {"profile_id": "profile-a", "asset_name": "a.wav", "status": "enrolled"}
    verify_result = {"profile_id": "profile-a", "score": 0.91, "threshold": 0.7, "matched": True}
    identify_result = {
        "candidates": [{"profile_id": "profile-a", "display_name": "A", "score": 0.91, "rank": 1}],
        "matched": True,
    }
    enroll_job_id = _insert_voiceprint_job("voiceprint_enroll", enroll_result, status="succeeded")
    verify_job_id = _insert_voiceprint_job("voiceprint_verify", verify_result, status="succeeded")
    identify_job_id = _insert_voiceprint_job(
        "voiceprint_identify",
        identify_result,
        status="succeeded",
    )

    enroll_payload = voiceprint_routes.get_voiceprint_job(enroll_job_id)
    verify_payload = voiceprint_routes.get_voiceprint_job(verify_job_id)
    identify_payload = voiceprint_routes.get_voiceprint_job(identify_job_id)

    assert enroll_payload["enrollment"] == enroll_result
    assert enroll_payload["verification"] is None
    assert verify_payload["verification"] == verify_result
    assert verify_payload["identification"] is None
    assert identify_payload["identification"] == identify_result
    assert identify_payload["enrollment"] is None


def test_voiceprint_job_endpoint_ignores_invalid_json_result() -> None:
    job_id = _insert_voiceprint_job(
        "voiceprint_verify",
        "not-json",
        status="failed",
        error_message="boom",
    )

    payload = voiceprint_routes.get_voiceprint_job(job_id)

    assert payload["status"] == "failed"
    assert payload["error_message"] == "boom"
    assert payload["verification"] is None
