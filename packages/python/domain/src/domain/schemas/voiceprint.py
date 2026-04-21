from pydantic import BaseModel, Field


class VoiceprintProfile(BaseModel):
    profile_id: str
    display_name: str
    model_key: str
    sample_count: int = 0


class VoiceprintVerificationResult(BaseModel):
    profile_id: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    matched: bool


class VoiceprintIdentificationCandidate(BaseModel):
    profile_id: str
    display_name: str
    score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)


class VoiceprintIdentificationResult(BaseModel):
    candidates: list[VoiceprintIdentificationCandidate]
    matched: bool
