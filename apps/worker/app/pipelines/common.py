from __future__ import annotations

from dataclasses import dataclass

from domain.schemas.transcript import Segment, TranscriptResult
from domain.schemas.voiceprint import VoiceprintIdentificationResult, VoiceprintVerificationResult
from model_adapters import AudioAsset, resolve_audio_asset_path


@dataclass(slots=True)
class TaskContext:
    job_id: str
    asset_name: str
    output_dir: str = "storage/jobs"

    @property
    def asset(self) -> AudioAsset:
        return AudioAsset(path=resolve_audio_asset_path(self.asset_name))


def normalize_audio_asset(asset_name: str) -> AudioAsset:
    return AudioAsset(path=f"storage/normalized/{asset_name}")


def build_transcript_result(transcript: TranscriptResult, diarization: list[Segment] | None = None) -> TranscriptResult:
    if not diarization:
        return transcript
    merged_segments: list[Segment] = []
    for index, segment in enumerate(transcript.segments):
        speaker = diarization[min(index, len(diarization) - 1)].speaker
        merged_segments.append(segment.model_copy(update={"speaker": speaker}))
    return TranscriptResult(text=transcript.text, language=transcript.language, segments=merged_segments)


def build_voiceprint_verification_result(result: VoiceprintVerificationResult) -> VoiceprintVerificationResult:
    return result


def build_voiceprint_identification_result(result: VoiceprintIdentificationResult) -> VoiceprintIdentificationResult:
    return result
