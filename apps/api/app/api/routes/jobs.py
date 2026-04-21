from fastapi import APIRouter, HTTPException

from ..schemas import JobListResponse
from ...services.job_service import job_service

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=JobListResponse)
def list_jobs() -> JobListResponse:
    items = [job_service.get_job(job.job_id) for job in job_service.list_jobs()]
    return JobListResponse(items=[item for item in items if item is not None])


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
