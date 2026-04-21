from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from domain.schemas.transcript import Segment, TranscriptResult
from domain.schemas.voiceprint import (
    VoiceprintIdentificationResult,
    VoiceprintVerificationResult,
)

ModelAvailability = Literal["available", "optional", "unavailable"]
PROJECT_ROOT = Path(__file__).resolve().parents[5]


@dataclass(slots=True)
class AudioAsset:
    path: str
    sample_rate: int = 16000
    channels: int = 1


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def resolve_model_reference(model_name: str) -> str:
    candidate = resolve_project_path(model_name)
    return str(candidate) if candidate.exists() else model_name


def resolve_audio_asset_path(asset_name: str) -> str:
    candidates = [
        resolve_project_path(Path("storage/uploads") / asset_name),
        resolve_project_path(Path("tests") / asset_name),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


class ASRAdapter(ABC):
    key: str
    display_name: str = ""
    provider: str = ""
    experimental: bool = False

    @property
    def availability(self) -> ModelAvailability:
        return "available"

    @abstractmethod
    def transcribe(self, asset: AudioAsset) -> TranscriptResult:
        raise NotImplementedError


class DiarizationAdapter(ABC):
    key: str
    display_name: str = ""
    provider: str = ""
    experimental: bool = False

    @property
    def availability(self) -> ModelAvailability:
        return "available"

    @abstractmethod
    def diarize(self, asset: AudioAsset) -> list[Segment]:
        raise NotImplementedError


class VoiceprintAdapter(ABC):
    key: str
    display_name: str = ""
    provider: str = ""
    experimental: bool = False

    @property
    def availability(self) -> ModelAvailability:
        return "available"

    @abstractmethod
    def enroll(self, asset: AudioAsset, profile_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def verify(self, asset: AudioAsset, profile_id: str, threshold: float) -> VoiceprintVerificationResult:
        raise NotImplementedError

    @abstractmethod
    def identify(self, asset: AudioAsset, top_k: int) -> VoiceprintIdentificationResult:
        raise NotImplementedError
