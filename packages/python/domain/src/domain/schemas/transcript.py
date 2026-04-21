from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

JobType = Literal[
    "transcription",
    "multi_speaker_transcription",
    "voiceprint_enroll",
    "voiceprint_verify",
    "voiceprint_identify",
]
JobStatus = Literal["pending", "queued", "running", "succeeded", "failed"]


class Segment(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = ""
    speaker: str | None = None
    confidence: float | None = None


class TranscriptResult(BaseModel):
    text: str
    language: str | None = None
    segments: list[Segment] = Field(default_factory=list)


class JobSummary(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    asset_name: str | None = None


class JobDetail(JobSummary):
    result: TranscriptResult | None = None
    error_message: str | None = None
