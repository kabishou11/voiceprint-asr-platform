from __future__ import annotations

from apps.api.app.services import voiceprint_service as voiceprint_module
from apps.api.app.services.voiceprint_service import voiceprint_service
from apps.worker.app.tasks import voiceprint as voiceprint_tasks


class _DummyVoiceprintAdapter:
    def __init__(self) -> None:
        self.enroll_calls: list[tuple[str, str]] = []

    def enroll(self, asset, profile_id: str, mode: str = "replace") -> dict:
        self.enroll_calls.append((profile_id, mode))
        return {
            "profile_id": profile_id,
            "asset": asset.path,
            "status": "enrolled",
            "mode": mode,
        }


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

    updated, first = voiceprint_service.enroll_profile(profile.profile_id, "声纹-女1.wav", mode="replace")
    assert updated.sample_count == 1
    assert first["mode"] == "replace"
    assert first["quality"]["available"] is True
    assert first["quality"]["duration_seconds"] >= 3.0

    updated, second = voiceprint_service.enroll_profile(profile.profile_id, "5分钟.wav", mode="append")
    assert updated.sample_count == 2
    assert second["mode"] == "append"
    assert second["quality"]["warnings"]

    updated, third = voiceprint_service.enroll_profile(profile.profile_id, "声纹-女1.wav", mode="replace")
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
