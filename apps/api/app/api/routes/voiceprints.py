from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _BaseModel

from apps.api.app.services import job_db
from apps.worker.app.celery_app import is_async_available
from apps.worker.app.tasks._base import update_job_result, update_job_status
from apps.worker.app.tasks.voiceprint import (
    enroll_voiceprint,
    identify_voiceprint,
    verify_voiceprint,
)

from ...services.voiceprint_service import voiceprint_service
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voiceprints", tags=["声纹管理"])


def _sync_voiceprint_fallback_enabled() -> bool:
    return os.environ.get("ALLOW_SYNC_VOICEPRINT_FALLBACK", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _raise_voiceprint_queue_unavailable(job_id: str, reason: str | None = None) -> None:
    message = (
        "异步声纹任务队列不可用，已拒绝在 API 请求线程中同步执行声纹模型。"
        "请启动 Redis/Celery Worker，或仅在本地调试时设置 "
        "ALLOW_SYNC_VOICEPRINT_FALLBACK=1。"
        f"原因：{reason or 'async_queue_unavailable'}"
    )
    update_job_result(job_id, status="failed", error_message=message)
    raise HTTPException(status_code=409, detail=message)


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
    profile = next(
        (item for item in voiceprint_service.list_profiles() if item.profile_id == profile_id),
        None,
    )
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

    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        stored_result = result[1]
    else:
        stored_result = result.model_dump() if hasattr(result, "model_dump") else result
    update_job_result(job_id, result=stored_result, status="succeeded")
    return result


def _job_receipt(job_id: str, status: str = "queued") -> VoiceprintAsyncReceipt:
    return VoiceprintAsyncReceipt(job_id=job_id, status=status)


def _decode_voiceprint_job_result(raw_result: Any) -> dict[str, Any] | None:
    if raw_result is None:
        return None
    if isinstance(raw_result, dict):
        return raw_result
    if not isinstance(raw_result, str) or not raw_result.strip():
        return None
    try:
        parsed = json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        logger.warning("声纹任务结果不是有效 JSON，忽略原始 result")
        return None
    return parsed if isinstance(parsed, dict) else None


@router.get(
    "/profiles",
    summary="获取声纹档案列表",
    description="返回当前所有声纹档案，包含 profile_id、display_name、sample_count 等基本信息。",
)
def list_profiles():
    return {"items": voiceprint_service.list_profiles()}


@router.get(
    "/groups",
    summary="获取声纹分组列表",
    description="返回所有声纹分组及其成员档案 ID 列表。分组用于多人转写时限定候选范围。",
)
def list_groups():
    with job_db.session() as db:
        groups = (
            db.query(job_db.VoiceprintGroupRecord)
            .order_by(job_db.VoiceprintGroupRecord.created_at.desc())
            .all()
        )
        result = []
        for group in groups:
            members = (
                db.query(job_db.VoiceprintGroupMemberRecord)
                .filter(job_db.VoiceprintGroupMemberRecord.group_id == group.group_id)
                .all()
            )
            result.append({
                "group_id": group.group_id,
                "display_name": group.display_name,
                "profile_ids": [m.profile_id for m in members],
            })
        return {"items": result}


class _CreateGroupRequest(_BaseModel):
    display_name: str


class _UpdateGroupRequest(_BaseModel):
    profile_ids: list[str] = []


@router.post(
    "/groups",
    summary="创建声纹分组",
    description="创建一个新的声纹分组，后续可将多个档案加入该分组，用于多人转写时限定候选范围。",
)
def create_group(payload: _CreateGroupRequest):
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="分组名称不能为空")
    group_id = f"group-{uuid4().hex[:8]}"
    with job_db.session() as db:
        db.add(job_db.VoiceprintGroupRecord(group_id=group_id, display_name=display_name))
        db.commit()
    return {"group_id": group_id, "display_name": display_name, "profile_ids": []}


@router.put(
    "/groups/{group_id}",
    summary="更新分组成员",
    description="替换指定分组的成员列表。传入 profile_ids 数组，会覆盖原有成员。",
)
def update_group(group_id: str, payload: _UpdateGroupRequest):
    with job_db.session() as db:
        group = db.get(job_db.VoiceprintGroupRecord, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="声纹分组不存在")
        db.query(job_db.VoiceprintGroupMemberRecord).filter(
            job_db.VoiceprintGroupMemberRecord.group_id == group_id
        ).delete()
        for profile_id in payload.profile_ids:
            db.add(job_db.VoiceprintGroupMemberRecord(group_id=group_id, profile_id=profile_id))
        db.commit()
    return {"group_id": group_id, "profile_ids": payload.profile_ids}


@router.get(
    "/profiles/{profile_id}",
    summary="获取声纹档案详情",
    description="返回指定档案的基本信息、已注册样本列表和最近操作历史。",
)
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
                job_db.JobRecord.job_type.in_(
                    {"voiceprint_enroll", "voiceprint_verify", "voiceprint_identify"}
                ),
                job_db.JobRecord.asset_name.in_(
                    db.query(job_db.VoiceprintSampleRecord.asset_name)
                    .filter(job_db.VoiceprintSampleRecord.profile_id == profile_id)
                    .scalar_subquery()
                ),
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


@router.post(
    "/profiles",
    response_model=CreateVoiceprintProfileResponse,
    summary="创建声纹档案",
    description="创建一个新的声纹档案。创建后需要调用注册接口写入基准音频样本。",
)
def create_profile(payload: CreateVoiceprintProfileRequest) -> CreateVoiceprintProfileResponse:
    profile = voiceprint_service.create_profile(payload.display_name, payload.model_key)
    return CreateVoiceprintProfileResponse(profile=profile)


@router.get(
    "/jobs/{job_id}",
    summary="查询声纹任务结果",
    description="查询声纹异步任务的最终结果。"
    "根据 job_type 返回 enrollment / verification / identification 结果。",
)
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
        parsed = _decode_voiceprint_job_result(record.result)
        if parsed:
            if record.job_type == "voiceprint_enroll":
                payload["enrollment"] = parsed
            elif record.job_type == "voiceprint_verify":
                payload["verification"] = parsed
            elif record.job_type == "voiceprint_identify":
                payload["identification"] = parsed
        return payload


@router.post(
    "/profiles/{profile_id}/enroll",
    response_model=EnrollVoiceprintResponse,
    summary="声纹注册（核心接口）",
    description="为指定档案注册一段基准音频。支持增量注册多个样本。"
    "异步模式下返回 job 回执，同步模式下直接返回注册结果。",
)
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
                mode=payload.mode,
            )
            return EnrollVoiceprintResponse(profile=profile, job=_job_receipt(job_id))
        except Exception as exc:
            logger.warning(f"声纹注册任务 {job_id} 异步提交失败: {exc}")
            if not _sync_voiceprint_fallback_enabled():
                _raise_voiceprint_queue_unavailable(job_id, str(exc))
    elif not _sync_voiceprint_fallback_enabled():
        _raise_voiceprint_queue_unavailable(job_id)

    enrolled_profile, enrollment = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.enroll_profile(
            profile_id,
            payload.asset_name,
            mode=payload.mode,
        ),
    )
    return EnrollVoiceprintResponse(
        profile=enrolled_profile,
        enrollment=VoiceprintEnrollmentResult(**enrollment),
    )


@router.post(
    "/verify",
    response_model=VerifyVoiceprintResponse,
    summary="声纹验证（核心接口）",
    description="判断一段待测音频是否属于指定声纹档案。返回相似度分数和是否通过阈值判断。"
    "threshold 范围 0~1，默认 0.7。",
)
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
            logger.warning(f"声纹验证任务 {job_id} 异步提交失败: {exc}")
            if not _sync_voiceprint_fallback_enabled():
                _raise_voiceprint_queue_unavailable(job_id, str(exc))
    elif not _sync_voiceprint_fallback_enabled():
        _raise_voiceprint_queue_unavailable(job_id)

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.verify(
            payload.profile_id,
            payload.probe_asset_name,
            payload.threshold,
        ),
    )
    return VerifyVoiceprintResponse(result=result)


@router.post(
    "/identify",
    response_model=IdentifyVoiceprintResponse,
    summary="声纹识别（核心接口）",
    description="在候选声纹库中识别最接近的档案。返回 top_k 个候选及其相似度分数。"
    "top_k 范围 1~10，默认 3。",
)
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
                profile_ids=payload.profile_ids,
            )
            return IdentifyVoiceprintResponse(job=_job_receipt(job_id))
        except Exception as exc:
            logger.warning(f"声纹识别任务 {job_id} 异步提交失败: {exc}")
            if not _sync_voiceprint_fallback_enabled():
                _raise_voiceprint_queue_unavailable(job_id, str(exc))
    elif not _sync_voiceprint_fallback_enabled():
        _raise_voiceprint_queue_unavailable(job_id)

    result = _run_sync_voiceprint_job(
        job_id,
        lambda: voiceprint_service.identify(
            probe_asset_name=payload.probe_asset_name,
            top_k=payload.top_k,
            profile_ids=payload.profile_ids,
        ),
    )
    return IdentifyVoiceprintResponse(result=result)
