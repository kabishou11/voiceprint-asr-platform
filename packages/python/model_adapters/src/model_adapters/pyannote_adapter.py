from __future__ import annotations

import importlib.util
from pathlib import Path

from domain.schemas.transcript import Segment
from model_adapters.base import (
    AudioAsset,
    DiarizationAdapter,
    has_cuda_runtime,
    require_available_model,
    resolve_model_reference,
)


class PyannoteDiarizationAdapter(DiarizationAdapter):
    key = "pyannote-community-1"
    display_name = "pyannote community-1"
    provider = "pyannote"
    experimental = True

    def __init__(self, model_name: str = "models/pyannote/speaker-diarization-community-1", enabled: bool = False) -> None:
        self.model_name = resolve_model_reference(model_name)
        self.enabled = enabled
        self.num_speakers: int | None = None
        self.min_speakers: int | None = None
        self.max_speakers: int | None = None
        self._pipeline = None
        self._last_regular_segments: list[Segment] = []
        self._last_exclusive_segments: list[Segment] = []

    @property
    def availability(self) -> str:
        has_local_model = _has_model_artifacts(self.model_name)
        if not has_local_model:
            return "unavailable"
        if not has_cuda_runtime():
            return "unavailable"
        if not self.enabled:
            return "optional"
        try:
            pyannote_spec = importlib.util.find_spec("pyannote.audio")
        except ModuleNotFoundError:
            pyannote_spec = None
        if pyannote_spec is None:
            return "unavailable"
        return "available"

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        from pyannote.audio import Pipeline

        if not _has_model_artifacts(self.model_name):
            raise RuntimeError(f"pyannote 本地模型不存在：{self.model_name}")
        self._pipeline = Pipeline.from_pretrained(self.model_name)
        return self._pipeline

    def diarize(self, asset: AudioAsset) -> list[Segment]:
        require_available_model(self.availability, model_label=self.display_name, purpose="说话人分离")
        if not self.enabled:
            raise RuntimeError("pyannote adapter is disabled in the current runtime")
        try:
            pyannote_spec = importlib.util.find_spec("pyannote.audio")
        except ModuleNotFoundError:
            pyannote_spec = None
        if pyannote_spec is None:
            raise RuntimeError("pyannote.audio is not installed in the current runtime")
        pipeline = self._load_pipeline()
        diarization = pipeline(
            asset.path,
            num_speakers=self.num_speakers,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
        )
        segments: list[Segment] = []
        speaker_map: dict[str, str] = {}
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            mapped = speaker_map.setdefault(speaker, f"SPEAKER_{len(speaker_map):02d}")
            segments.append(
                Segment(
                    start_ms=max(0, int(turn.start * 1000)),
                    end_ms=max(0, int(turn.end * 1000)),
                    text="",
                    speaker=mapped,
                    confidence=0.95,
                )
            )
        self._last_regular_segments = segments
        self._last_exclusive_segments = self._build_exclusive_segments(segments)
        if self._last_exclusive_segments:
            return self._last_exclusive_segments
        return segments

    def get_last_outputs(self) -> dict[str, list[Segment]]:
        return {
            "regular": [segment.model_copy() for segment in self._last_regular_segments],
            "exclusive": [segment.model_copy() for segment in self._last_exclusive_segments],
        }

    def _build_exclusive_segments(self, segments: list[Segment]) -> list[Segment]:
        if not segments:
            return []
        ordered = sorted(
            [segment.model_copy(update={"text": ""}) for segment in segments if segment.end_ms > segment.start_ms],
            key=lambda item: (item.start_ms, item.end_ms, item.speaker or ""),
        )
        if not ordered:
            return []

        exclusive: list[Segment] = [ordered[0]]
        for current in ordered[1:]:
            previous = exclusive[-1]
            if current.speaker == previous.speaker and current.start_ms <= previous.end_ms:
                exclusive[-1] = previous.model_copy(
                    update={
                        "end_ms": max(previous.end_ms, current.end_ms),
                        "confidence": _max_confidence(previous.confidence, current.confidence),
                    }
                )
                continue

            if current.start_ms < previous.end_ms:
                pivot = max(previous.start_ms, min(current.end_ms, round((previous.end_ms + current.start_ms) / 2)))
                exclusive[-1] = previous.model_copy(update={"end_ms": max(previous.start_ms, pivot)})
                current = current.model_copy(update={"start_ms": max(pivot, current.start_ms)})

            if current.end_ms <= current.start_ms:
                continue

            exclusive.append(current)
        return [segment for segment in exclusive if segment.end_ms > segment.start_ms]


def _has_model_artifacts(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.exists():
        return False
    if candidate.is_file():
        return candidate.name != ".gitkeep"
    required_names = {
        "config.yaml",
        "config.yml",
        "pytorch_model.bin",
        "model.safetensors",
        "pipeline.yaml",
        "pyannote_pipeline.yaml",
    }
    return any(item.is_file() and item.name in required_names for item in candidate.rglob("*"))


def _max_confidence(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
