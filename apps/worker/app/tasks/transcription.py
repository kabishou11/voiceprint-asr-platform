from __future__ import annotations

from domain.schemas.transcript import TranscriptResult
from model_adapters import resolve_audio_asset_path

from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry


def run_transcription(job_id: str, asset_name: str, model_key: str = "funasr-nano") -> TranscriptResult:
    registry = get_worker_registry()
    adapter = registry.get_asr(model_key)
    asset = preprocess_audio(adapter_asset(asset_name))
    return adapter.transcribe(asset)


def adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))
