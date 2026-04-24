from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from apps.worker.app.celery_app import is_async_available
from apps.worker.app.tasks._base import update_job_result, update_job_status
from apps.worker.app.tasks.voiceprint import (
    enroll_voiceprint,
    identify_voiceprint,
    verify_voiceprint,
)

from apps.api.app.services import job_db
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
    VoiceprintProfile,
)
from ...services.voiceprint_service import voiceprint_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voiceprints", tags=["voiceprints"])


# ============ 辅助函数 ============


def _create_job_record(
    job_type: str,
    asset_name: str,
    profile_id: str | None = None,
    threshold: float | None = None,
    top_k: int | None = None,
) -> str:
    """创建 job 记录，返回 job_id。"""
    job_id = str(uuid4())
    now = datetime.now(timezone.utc)
    with job_db.session() as db:
        record = job_db.JobRecord(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            asset_name=asset_name,
            result=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()
    return job_id


def _get_profile_or_404(profile_id: str) -> VoiceprintProfile:
    profile = next((item for item in voiceprint_service.list_profiles() if item.profile_id == profile_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="声纹档案不存在")
    return profile


def _run_sync_voiceprint_job(job_id: str, runner):
    update_job_status(job_id, "running")
    try:
        result = runner()
    except KeyError as exc:
        update_job_result(job_id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        update_job_result(job_id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        update_job_result(job_id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        update_job_result(job_id, status="failed", error_message=str(exc))
        raise

    stored_result = result.model_dump() if hasattr(result, "model_dump") else result
    update_job_result(job_id, result=stored_result, status="succeeded")
    return result


# ============ 档案管理路由（同步，无 job） ============


@router.get("/profiles")
def list_profiles():
    return {"items": voiceprint_service.list_profiles()}


@router.post("/profiles", response_model=CreateVoiceprintProfileResponse)
def create_profile(payload: CreateVoiceprintProfileRequest) -> CreateVoiceprintProfileResponse:
    profile = voiceprint_service.create_profile(payload.display_name, payload.model_key)
    return CreateVoiceprintProfileResponse(profile=profile)


# ============ 声纹任务路由（通过 Celery 队列） ============


@router.post("/profiles/{profile_id}/enroll", response_model=EnrollVoiceprintResponse)
def enroll_profile(profile_id: str, payload: EnrollVoiceprintRequest) -> EnrollVoiceprintResponse:
    profile = _get_profile_or_404(profile_id)
    job_id = _create_job_record(
        job_type="voiceprint_enroll",
        asset_name=payload.asset_name,
        profile_id=profile_id,
    )

    if is_async_available():
        try:
            result = enroll_voiceprint(
                job_id=job_id,
                asset_name=payload.asset_name,
                profile_id=profile_id,
            )
            return EnrollVoiceprintResponse(
                profile=profile,
                enrollment=VoiceprintEnrollmentResult(**result),
                job_id=job_id,
            )
        except Exception as exc:
            logger.warning(f"声纹注册任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    enrolled_profile, enrollment = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.enroll_profile(profile_id, payload.asset_name),
    )
    return EnrollVoiceprintResponse(
        profile=enrolled_profile,
        enrollment=VoiceprintEnrollmentResult(**enrollment),
        job_id=job_id,
    )


@router.post("/verify", response_model=VerifyVoiceprintResponse)
def verify(payload: VerifyVoiceprintRequest) -> VerifyVoiceprintResponse:
    _get_profile_or_404(payload.profile_id)
    job_id = _create_job_record(
        job_type="voiceprint_verify",
        asset_name=payload.probe_asset_name,
        profile_id=payload.profile_id,
        threshold=payload.threshold,
    )

    if is_async_available():
        try:
            result = verify_voiceprint(
                job_id=job_id,
                asset_name=payload.probe_asset_name,
                profile_id=payload.profile_id,
                threshold=payload.threshold,
            )
            return VerifyVoiceprintResponse(result=result, job_id=job_id)
        except Exception as exc:
            logger.warning(f"声纹验证任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.verify(payload.profile_id, payload.probe_asset_name, payload.threshold),
    )
    return VerifyVoiceprintResponse(result=result, job_id=job_id)


@router.post("/identify", response_model=IdentifyVoiceprintResponse)
def identify(payload: IdentifyVoiceprintRequest) -> IdentifyVoiceprintResponse:
    job_id = _create_job_record(
        job_type="voiceprint_identify",
        asset_name=payload.probe_asset_name,
        top_k=payload.top_k,
    )

    if is_async_available():
        try:
            result = identify_voiceprint(
                job_id=job_id,
                asset_name=payload.probe_asset_name,
                top_k=payload.top_k,
            )
            return IdentifyVoiceprintResponse(result=result, job_id=job_id)
        except Exception as exc:
            logger.warning(f"声纹识别任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.identify(probe_asset_name=payload.probe_asset_name, top_k=payload.top_k),
    )
    return IdentifyVoiceprintResponse(result=result, job_id=job_id)
