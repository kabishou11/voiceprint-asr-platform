from __future__ import annotations

from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
)

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
