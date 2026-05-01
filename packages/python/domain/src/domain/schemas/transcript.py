from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

JobType = Literal[
    "transcription",
    "multi_speaker_transcription",
    "voiceprint_enroll",
    "voiceprint_verify",
    "voiceprint_identify",
]
JobStatus = Literal["pending", "queued", "running", "succeeded", "failed", "canceled"]


class Segment(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = ""
    speaker: str | None = None
    confidence: float | None = None


class TranscriptTimeline(BaseModel):
    label: str
    source: str
    segments: list[Segment] = Field(default_factory=list)


class VoiceprintMatchCandidate(BaseModel):
    profile_id: str
    display_name: str
    score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)


class VoiceprintSpeakerMatch(BaseModel):
    speaker: str
    scope_mode: Literal["none", "all", "group"] = "none"
    scope_group_id: str | None = None
    candidate_profile_ids: list[str] = Field(default_factory=list)
    candidates: list[VoiceprintMatchCandidate] = Field(default_factory=list)
    matched: bool = False
    error: str | None = None


class TranscriptMetadata(BaseModel):
    timelines: list[TranscriptTimeline] = Field(default_factory=list)
    diarization_model: str | None = None
    alignment_source: str | None = None
    voiceprint_matches: list[VoiceprintSpeakerMatch] = Field(default_factory=list)


class TranscriptResult(BaseModel):
    text: str
    language: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    metadata: TranscriptMetadata | None = None


class JobSummary(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asset_name: str | None = None


class JobDetail(JobSummary):
    result: TranscriptResult | None = None
    error_message: str | None = None
    status_explanation: str | None = None
