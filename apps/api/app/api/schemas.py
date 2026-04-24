from enum import Enum
from typing import Literal

from pydantic import BaseModel

from domain.schemas.transcript import JobDetail, TranscriptResult
from domain.schemas.voiceprint import VoiceprintIdentificationResult, VoiceprintProfile, VoiceprintVerificationResult

ModelAvailability = Literal["available", "optional", "unavailable"]


class ModelStatus(str, Enum):
    unloaded = "unloaded"
    loading = "loading"
    loaded = "loaded"
    load_failed = "load_failed"


class HealthResponse(BaseModel):
    status: str
    app_name: str
    broker_available: bool = False
    worker_available: bool = False
    async_available: bool = False
    execution_mode: Literal["async", "sync"] = "sync"
    broker_error: str | None = None
    worker_error: str | None = None


class ModelInfo(BaseModel):
    key: str
    display_name: str
    task: str
    provider: str
    availability: ModelAvailability
    experimental: bool = False


class JobListResponse(BaseModel):
    items: list[JobDetail]


class CreateTranscriptionRequest(BaseModel):
    asset_name: str
    diarization_model: str | None = None
    hotwords: list[str] | None = None
    language: str = "zh-cn"
    vad_enabled: bool = False
    itn: bool = True
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None


class CreateTranscriptionResponse(BaseModel):
    job: JobDetail


class TranscriptResponse(BaseModel):
    job: JobDetail
    transcript: TranscriptResult | None = None


class SpeakerMinuteStatsResponse(BaseModel):
    speaker: str
    segment_count: int
    duration_ms: int


class MeetingMinutesResponse(BaseModel):
    job_id: str
    title: str
    summary: str
    key_points: list[str]
    topics: list[str]
    decisions: list[str]
    action_items: list[str]
    risks: list[str]
    keywords: list[str]
    speaker_stats: list[SpeakerMinuteStatsResponse]
    markdown: str
    mode: Literal["local", "llm"] = "local"
    model: str | None = None
    reasoning: str | None = None


class UploadAssetResponse(BaseModel):
    asset_name: str
    original_filename: str
    size: int


class CreateVoiceprintProfileRequest(BaseModel):
    display_name: str
    model_key: str = "3dspeaker-embedding"


class CreateVoiceprintProfileResponse(BaseModel):
    profile: VoiceprintProfile


class VoiceprintEnrollmentResult(BaseModel):
    profile_id: str
    asset_name: str
    status: str
    mode: str


class EnrollVoiceprintRequest(BaseModel):
    asset_name: str


class EnrollVoiceprintResponse(BaseModel):
    profile: VoiceprintProfile
    enrollment: VoiceprintEnrollmentResult
    job_id: str | None = None


class VerifyVoiceprintRequest(BaseModel):
    profile_id: str
    probe_asset_name: str
    threshold: float = 0.7


class VerifyVoiceprintResponse(BaseModel):
    result: VoiceprintVerificationResult
    job_id: str | None = None


class IdentifyVoiceprintRequest(BaseModel):
    probe_asset_name: str
    top_k: int = 3


class IdentifyVoiceprintResponse(BaseModel):
    result: VoiceprintIdentificationResult
    job_id: str | None = None


# GPU and model management schemas

class GPUInfo(BaseModel):
    name: str | None = None
    total_memory_mb: int | None = None
    used_memory_mb: int | None = None
    cuda_available: bool = False


class ModelInfoWithStatus(BaseModel):
    key: str
    display_name: str
    task: str
    provider: str
    availability: ModelAvailability
    status: ModelStatus
    gpu_memory_mb: int | None = None
    load_progress: float | None = None
    error: str | None = None
    experimental: bool = False


class ModelLoadResponse(BaseModel):
    key: str
    status: ModelStatus
    gpu_memory_mb: int | None = None
    error: str | None = None


class ModelUnloadResponse(BaseModel):
    key: str
    status: ModelStatus
    released_mb: int | None = None


class ModelListWithGPUResponse(BaseModel):
    items: list[ModelInfoWithStatus]
    gpu: GPUInfo
