from __future__ import annotations

from domain.schemas.transcript import TranscriptResult
from model_adapters import resolve_audio_asset_path

from ..pipelines.alignment import align_transcript_with_speakers
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry


def run_multi_speaker_transcription(
    job_id: str,
    asset_name: str,
    asr_model_key: str = "funasr-nano",
    diarization_model_key: str = "3dspeaker-diarization",
) -> TranscriptResult:
    registry = get_worker_registry()
    asset = preprocess_audio(adapter_asset(asset_name))
    transcript = registry.get_asr(asr_model_key).transcribe(asset)
    diarization_segments = registry.get_diarization(diarization_model_key).diarize(asset)
    return align_transcript_with_speakers(transcript, diarization_segments)


def adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))
