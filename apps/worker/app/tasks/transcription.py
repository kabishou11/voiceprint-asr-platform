from __future__ import annotations

from domain.schemas.transcript import TranscriptResult
from model_adapters import resolve_audio_asset_path

from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry


def run_transcription(
    job_id: str,
    asset_name: str,
    model_key: str = "funasr-nano",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = False,
    itn: bool = True,
) -> TranscriptResult:
    registry = get_worker_registry()
    adapter = registry.get_asr(model_key)
    asset = preprocess_audio(adapter_asset(asset_name))

    # 如适配器支持热词参数，注入热词
    if hotwords and hasattr(adapter, "hotwords"):
        adapter.hotwords = hotwords
    if hasattr(adapter, "language"):
        adapter.language = language
    if hasattr(adapter, "vad_enabled"):
        adapter.vad_enabled = vad_enabled
    if hasattr(adapter, "itn"):
        adapter.itn = itn

    return adapter.transcribe(asset)


def adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))
