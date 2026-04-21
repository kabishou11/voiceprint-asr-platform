from __future__ import annotations

from domain.schemas.voiceprint import VoiceprintIdentificationResult, VoiceprintVerificationResult
from model_adapters import resolve_audio_asset_path

from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry


def enroll_voiceprint(job_id: str, asset_name: str, profile_id: str, model_key: str = "3dspeaker-embedding") -> dict:
    registry = get_worker_registry()
    adapter = registry.get_voiceprint(model_key)
    asset = preprocess_audio(adapter_asset(asset_name))
    return adapter.enroll(asset=asset, profile_id=profile_id)


def verify_voiceprint(
    job_id: str,
    asset_name: str,
    profile_id: str,
    threshold: float,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintVerificationResult:
    registry = get_worker_registry()
    adapter = registry.get_voiceprint(model_key)
    asset = preprocess_audio(adapter_asset(asset_name))
    return adapter.verify(asset=asset, profile_id=profile_id, threshold=threshold)


def identify_voiceprint(
    job_id: str,
    asset_name: str,
    top_k: int,
    model_key: str = "3dspeaker-embedding",
) -> VoiceprintIdentificationResult:
    registry = get_worker_registry()
    adapter = registry.get_voiceprint(model_key)
    asset = preprocess_audio(adapter_asset(asset_name))
    return adapter.identify(asset=asset, top_k=top_k)


def adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))
