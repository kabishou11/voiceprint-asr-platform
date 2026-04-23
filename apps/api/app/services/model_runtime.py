from __future__ import annotations

from functools import lru_cache

from ..core.config import get_settings
from model_adapters import ModelRegistry, build_default_registry


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    settings = get_settings()
    return build_default_registry(
        funasr_model=settings.funasr_model,
        three_d_speaker_model=settings.three_d_speaker_model,
        pyannote_model=settings.pyannote_model,
        enable_pyannote=settings.enable_pyannote,
        enable_3d_speaker_adaptive_clustering=settings.enable_3d_speaker_adaptive_clustering,
    )
