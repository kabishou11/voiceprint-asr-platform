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
    VoiceprintAsyncReceipt,
    VoiceprintEnrollmentResult,
    VoiceprintProfile,
)
from ...services.voiceprint_service import voiceprint_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voiceprints", tags=["voiceprints"])


def _create_job_record(
    job_type: str,
    asset_name: str,
    profile_id: str | None = None,
    threshold: float | None = None,
    top_k: int | None = None,
) -> str:
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


def _job_receipt(job_id: str, status: str = "queued") -> VoiceprintAsyncReceipt:
    return VoiceprintAsyncReceipt(job_id=job_id, status=status)


@router.get("/profiles")
def list_profiles():
    return {"items": voiceprint_service.list_profiles()}


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    profile = _get_profile_or_404(profile_id)
    with job_db.session() as db:
        samples = (
            db.query(job_db.VoiceprintSampleRecord)
            .filter(job_db.VoiceprintSampleRecord.profile_id == profile_id)
            .order_by(job_db.VoiceprintSampleRecord.created_at.desc())
            .all()
        )
        history = (
            db.query(job_db.JobRecord)
            .filter(
                job_db.JobRecord.asset_name.isnot(None),
                job_db.JobRecord.job_type.in_({"voiceprint_enroll", "voiceprint_verify", "voiceprint_identify"}),
            )
            .order_by(job_db.JobRecord.created_at.desc())
            .limit(20)
            .all()
        )
        return {
            "profile": profile,
            "samples": [
                {
                    "sample_id": s.sample_id,
                    "asset_name": s.asset_name,
                    "source_job_id": s.source_job_id,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in samples
            ],
            "history": [
                {
                    "job_id": j.job_id,
                    "job_type": j.job_type,
                    "status": j.status,
                    "asset_name": j.asset_name,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in history
            ],
        }


@router.post("/profiles", response_model=CreateVoiceprintProfileResponse)
def create_profile(payload: CreateVoiceprintProfileRequest) -> CreateVoiceprintProfileResponse:
    profile = voiceprint_service.create_profile(payload.display_name, payload.model_key)
    return CreateVoiceprintProfileResponse(profile=profile)


@router.get("/jobs/{job_id}")
def get_voiceprint_job(job_id: str):
    with job_db.session() as db:
        record = db.get(job_db.JobRecord, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if record.job_type not in {"voiceprint_enroll", "voiceprint_verify", "voiceprint_identify"}:
            raise HTTPException(status_code=404, detail="Voiceprint job not found")

        payload = {
            "job_id": record.job_id,
            "job_type": record.job_type,
            "status": record.status,
            "asset_name": record.asset_name,
            "error_message": record.error_message,
            "enrollment": None,
            "verification": None,
            "identification": None,
        }
        if record.result:
            import json

            parsed = json.loads(record.result)
            if record.job_type == "voiceprint_enroll":
                payload["enrollment"] = parsed
            elif record.job_type == "voiceprint_verify":
                payload["verification"] = parsed
            elif record.job_type == "voiceprint_identify":
                payload["identification"] = parsed
        return payload


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
            enroll_voiceprint(
                job_id=job_id,
                asset_name=payload.asset_name,
                profile_id=profile_id,
            )
            return EnrollVoiceprintResponse(profile=profile, job=_job_receipt(job_id))
        except Exception as exc:
            logger.warning(f"声纹注册任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    enrolled_profile, enrollment = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.enroll_profile(profile_id, payload.asset_name),
    )
    return EnrollVoiceprintResponse(
        profile=enrolled_profile,
        enrollment=VoiceprintEnrollmentResult(**enrollment),
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
            verify_voiceprint(
                job_id=job_id,
                asset_name=payload.probe_asset_name,
                profile_id=payload.profile_id,
                threshold=payload.threshold,
            )
            return VerifyVoiceprintResponse(job=_job_receipt(job_id))
        except Exception as exc:
            logger.warning(f"声纹验证任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.verify(payload.profile_id, payload.probe_asset_name, payload.threshold),
    )
    return VerifyVoiceprintResponse(result=result)


@router.post("/identify", response_model=IdentifyVoiceprintResponse)
def identify(payload: IdentifyVoiceprintRequest) -> IdentifyVoiceprintResponse:
    job_id = _create_job_record(
        job_type="voiceprint_identify",
        asset_name=payload.probe_asset_name,
        top_k=payload.top_k,
    )

    if is_async_available():
        try:
            identify_voiceprint(
                job_id=job_id,
                asset_name=payload.probe_asset_name,
                top_k=payload.top_k,
            )
            return IdentifyVoiceprintResponse(job=_job_receipt(job_id))
        except Exception as exc:
            logger.warning(f"声纹识别任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.identify(probe_asset_name=payload.probe_asset_name, top_k=payload.top_k),
    )
    return IdentifyVoiceprintResponse(result=result)
