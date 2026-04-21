from fastapi import APIRouter, HTTPException

from ..schemas import (
    CreateVoiceprintProfileRequest,
    CreateVoiceprintProfileResponse,
    EnrollVoiceprintRequest,
    EnrollVoiceprintResponse,
    IdentifyVoiceprintRequest,
    IdentifyVoiceprintResponse,
    VerifyVoiceprintRequest,
    VerifyVoiceprintResponse,
    VoiceprintEnrollmentResult,
)
from ...services.voiceprint_service import voiceprint_service

router = APIRouter(prefix="/voiceprints", tags=["voiceprints"])


@router.get("/profiles")
def list_profiles():
    return {"items": voiceprint_service.list_profiles()}


@router.post("/profiles", response_model=CreateVoiceprintProfileResponse)
def create_profile(payload: CreateVoiceprintProfileRequest) -> CreateVoiceprintProfileResponse:
    profile = voiceprint_service.create_profile(payload.display_name, payload.model_key)
    return CreateVoiceprintProfileResponse(profile=profile)


@router.post("/profiles/{profile_id}/enroll", response_model=EnrollVoiceprintResponse)
def enroll_profile(profile_id: str, payload: EnrollVoiceprintRequest) -> EnrollVoiceprintResponse:
    try:
        profile, enrollment = voiceprint_service.enroll_profile(profile_id, payload.asset_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EnrollVoiceprintResponse(profile=profile, enrollment=VoiceprintEnrollmentResult(**enrollment))


@router.post("/verify", response_model=VerifyVoiceprintResponse)
def verify(payload: VerifyVoiceprintRequest) -> VerifyVoiceprintResponse:
    result = voiceprint_service.verify(payload.profile_id, payload.probe_asset_name, payload.threshold)
    return VerifyVoiceprintResponse(result=result)


@router.post("/identify", response_model=IdentifyVoiceprintResponse)
def identify(payload: IdentifyVoiceprintRequest) -> IdentifyVoiceprintResponse:
    result = voiceprint_service.identify(probe_asset_name=payload.probe_asset_name, top_k=payload.top_k)
    return IdentifyVoiceprintResponse(result=result)
