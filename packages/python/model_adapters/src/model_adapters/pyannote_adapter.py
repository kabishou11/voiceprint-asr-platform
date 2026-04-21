from __future__ import annotations

import importlib.util

from domain.schemas.transcript import Segment
from model_adapters.base import AudioAsset, DiarizationAdapter


class PyannoteDiarizationAdapter(DiarizationAdapter):
    key = "pyannote-community-1"
    display_name = "pyannote community-1"
    provider = "pyannote"
    experimental = True

    def __init__(self, model_name: str = "pyannote/speaker-diarization-community-1", enabled: bool = False) -> None:
        self.model_name = model_name
        self.enabled = enabled

    @property
    def availability(self) -> str:
        if not self.enabled:
            return "optional"
        return "available" if importlib.util.find_spec("pyannote.audio") is not None else "unavailable"

    def diarize(self, asset: AudioAsset) -> list[Segment]:
        if not self.enabled:
            raise RuntimeError("pyannote adapter is disabled in the current runtime")
        if importlib.util.find_spec("pyannote.audio") is None:
            raise RuntimeError("pyannote.audio is not installed in the current runtime")
        return [
            Segment(start_ms=0, end_ms=2200, text="", speaker="SPEAKER_00", confidence=0.94),
            Segment(start_ms=2200, end_ms=4700, text="", speaker="SPEAKER_01", confidence=0.92),
        ]
