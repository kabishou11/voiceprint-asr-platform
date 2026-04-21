from typing import Literal

from pydantic import BaseModel

from domain.schemas.transcript import JobDetail, TranscriptResult
from domain.schemas.voiceprint import VoiceprintIdentificationResult, VoiceprintProfile, VoiceprintVerificationResult

ModelAvailability = Literal["available", "optional", "unavailable"]


class HealthResponse(BaseModel):
    status: str
    app_name: str


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


class CreateTranscriptionResponse(BaseModel):
    job: JobDetail


class TranscriptResponse(BaseModel):
    job: JobDetail
    transcript: TranscriptResult | None = None


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


class VerifyVoiceprintRequest(BaseModel):
    profile_id: str
    probe_asset_name: str
    threshold: float = 0.7


class VerifyVoiceprintResponse(BaseModel):
    result: VoiceprintVerificationResult


class IdentifyVoiceprintRequest(BaseModel):
    probe_asset_name: str
    top_k: int = 3


class IdentifyVoiceprintResponse(BaseModel):
    result: VoiceprintIdentificationResult
