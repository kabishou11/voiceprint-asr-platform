from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.worker.app.celery_app import is_async_available
from apps.worker.app.tasks._base import update_job_result, update_job_status
from apps.worker.app.tasks.diarization import get_diarization_task, run_diarization

from ...services import job_db
from ...services.job_service import job_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diarizations", tags=["diarizations"])


class CreateDiarizationRequest(BaseModel):
    asset_name: str
    diarization_model: str = "3dspeaker-diarization"
    num_speakers: int | None = Field(default=None, ge=1, le=32)
    min_speakers: int | None = Field(default=None, ge=1, le=32)
    max_speakers: int | None = Field(default=None, ge=1, le=32)


class CreateDiarizationResponse(BaseModel):
    job_id: str
    status: str


@router.post("", response_model=CreateDiarizationResponse)
def create_diarization(payload: CreateDiarizationRequest) -> CreateDiarizationResponse:
    job_id = str(uuid4())
    now = datetime.now(timezone.utc)

    with job_db.session() as db:
        record = job_db.JobRecord(
            job_id=job_id,
            job_type="diarization",
            status="queued",
            asset_name=payload.asset_name,
            result=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()

    if is_async_available():
        try:
            task = get_diarization_task()
            if task is not None and hasattr(task, "apply_async"):
                task.apply_async(
                    args=[job_id, payload.asset_name, payload.diarization_model],
                    kwargs={
                        "num_speakers": payload.num_speakers,
                        "min_speakers": payload.min_speakers,
                        "max_speakers": payload.max_speakers,
                    },
                )
                logger.info(f"说话人分离任务 {job_id} 已提交到队列")
                return CreateDiarizationResponse(job_id=job_id, status="queued")
        except Exception as exc:
            logger.warning(f"说话人分离任务 {job_id} 异步提交失败，回退到同步执行: {exc}")

    update_job_status(job_id, "running")
    try:
        result = run_diarization(
            job_id=job_id,
            asset_name=payload.asset_name,
            diarization_model_key=payload.diarization_model,
            num_speakers=payload.num_speakers,
            min_speakers=payload.min_speakers,
            max_speakers=payload.max_speakers,
        )
        update_job_result(job_id, result=result, status="succeeded")
        return CreateDiarizationResponse(job_id=job_id, status="succeeded")
    except Exception as exc:
        update_job_result(job_id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}")
def get_diarization(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.job_type != "diarization":
        raise HTTPException(status_code=404, detail="Diarization job not found")
    return job
