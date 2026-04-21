from __future__ import annotations

from model_adapters import AudioAsset


def preprocess_audio(asset: AudioAsset) -> AudioAsset:
    return AudioAsset(path=asset.path, sample_rate=16000, channels=1)
