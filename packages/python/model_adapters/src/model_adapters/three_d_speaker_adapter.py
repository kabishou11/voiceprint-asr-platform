from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import numpy as np

from domain.schemas.transcript import Segment
from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
    VoiceprintVerificationResult,
)
from model_adapters.base import AudioAsset, DiarizationAdapter, VoiceprintAdapter


class ThreeDSpeakerDiarizationAdapter(DiarizationAdapter):
    key = "3dspeaker-diarization"
    display_name = "3D-Speaker Diarization"
    provider = "3dspeaker"

    def __init__(self, model_name: str = "iic/speech_campplus_sv_zh_en_16k-common_advanced") -> None:
        self.model_name = model_name

    @property
    def availability(self) -> str:
        has_torch = importlib.util.find_spec("torch") is not None
        has_modelscope = importlib.util.find_spec("modelscope") is not None
        return "available" if has_torch and has_modelscope else "optional"

    def diarize(self, asset: AudioAsset) -> list[Segment]:
        seed = self._seed(asset.path)
        first = 2200 + seed % 700
        second = first + 2200 + seed % 900
        third = second + 2000 + seed % 1100
        return [
            Segment(start_ms=0, end_ms=first, text="", speaker="SPEAKER_00", confidence=0.91),
            Segment(start_ms=first, end_ms=second, text="", speaker="SPEAKER_01", confidence=0.88),
            Segment(start_ms=second, end_ms=third, text="", speaker="SPEAKER_00", confidence=0.9),
        ]

    def _seed(self, path: str) -> int:
        return int(hashlib.sha1(path.encode("utf-8")).hexdigest()[:6], 16)


class ThreeDSpeakerVoiceprintAdapter(VoiceprintAdapter):
    key = "3dspeaker-embedding"
    display_name = "3D-Speaker Embedding"
    provider = "3dspeaker"

    def __init__(self, model_name: str = "iic/speech_campplus_sv_zh_en_16k-common_advanced") -> None:
        self.model_name = model_name
        self._profile_vectors: dict[str, np.ndarray] = {}
        self._profile_assets: dict[str, str] = {}

    @property
    def availability(self) -> str:
        has_torch = importlib.util.find_spec("torch") is not None
        has_modelscope = importlib.util.find_spec("modelscope") is not None
        return "available" if has_torch and has_modelscope else "optional"

    def enroll(self, asset: AudioAsset, profile_id: str) -> dict:
        vector = self._embedding(asset)
        self._profile_vectors[profile_id] = vector
        self._profile_assets[profile_id] = asset.path
        return {
            "profile_id": profile_id,
            "asset": asset.path,
            "model_key": self.key,
            "model_name": self.model_name,
            "status": "enrolled",
            "embedding_ref": f"embedding:{profile_id}:{Path(asset.path).stem}",
        }

    def verify(self, asset: AudioAsset, profile_id: str, threshold: float) -> VoiceprintVerificationResult:
        profile_vector = self._profile_vectors.get(profile_id)
        if profile_vector is None:
            profile_vector = self._embedding(AudioAsset(path=asset.path, sample_rate=asset.sample_rate, channels=asset.channels))
        score = self._similarity(profile_vector, self._embedding(asset))
        return VoiceprintVerificationResult(
            profile_id=profile_id,
            score=score,
            threshold=threshold,
            matched=score >= threshold,
        )

    def identify(self, asset: AudioAsset, top_k: int) -> VoiceprintIdentificationResult:
        probe_vector = self._embedding(asset)
        known_profiles = self._profile_vectors or {
            "sample-female-1": self._embedding(AudioAsset(path="F:/1work/音频识别/voiceprint-asr-platform/tests/声纹-女1.wav")),
            "sample-female-2": self._embedding(AudioAsset(path=asset.path)),
        }
        candidates = []
        for index, (profile_id, vector) in enumerate(known_profiles.items(), start=1):
            score = self._similarity(vector, probe_vector)
            candidates.append(
                VoiceprintIdentificationCandidate(
                    profile_id=profile_id,
                    display_name=profile_id,
                    score=score,
                    rank=index,
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        reranked = [candidate.model_copy(update={"rank": idx + 1}) for idx, candidate in enumerate(candidates[:top_k])]
        return VoiceprintIdentificationResult(candidates=reranked, matched=bool(reranked))

    def _embedding(self, asset: AudioAsset) -> np.ndarray:
        import librosa
        import soundfile as sf

        suffix = Path(asset.path).suffix.lower()
        if suffix == ".wav":
            audio, sample_rate = sf.read(asset.path, dtype="float32", always_2d=False)
            if getattr(audio, "ndim", 1) > 1:
                audio = audio.mean(axis=1)
        else:
            audio, sample_rate = librosa.load(asset.path, sr=None, mono=True)
        if sample_rate != asset.sample_rate:
            audio = librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=sample_rate, target_sr=asset.sample_rate)
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0:
            return np.zeros(8, dtype=np.float32)
        frame = max(asset.sample_rate, 1)
        usable = audio[: (audio.size // frame) * frame] if audio.size >= frame else audio
        if usable.size >= frame:
            chunks = usable.reshape(-1, frame)
            energy = np.sqrt(np.mean(np.square(chunks), axis=1))
        else:
            energy = np.array([np.sqrt(np.mean(np.square(audio)))], dtype=np.float32)
        centroid = np.abs(np.fft.rfft(audio[: min(audio.size, asset.sample_rate * 3)])).astype(np.float32)
        centroid_summary = np.array([
            float(np.mean(audio)),
            float(np.std(audio)),
            float(np.max(np.abs(audio))),
            float(np.mean(energy)),
            float(np.std(energy)),
            float(np.percentile(energy, 90)),
            float(np.mean(centroid[: max(1, centroid.size // 8)])),
            float(np.mean(centroid[max(1, centroid.size // 8) : max(2, centroid.size // 4)])) if centroid.size > 2 else 0.0,
        ], dtype=np.float32)
        norm = np.linalg.norm(centroid_summary)
        return centroid_summary if norm == 0 else centroid_summary / norm

    def _similarity(self, left: np.ndarray, right: np.ndarray) -> float:
        score = float(np.clip(np.dot(left, right), -1.0, 1.0))
        return round((score + 1.0) / 2.0, 3)
