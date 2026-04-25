from fastapi import APIRouter, HTTPException, Query

from ..schemas import JobListResponse, PaginationMeta
from ...services.job_service import job_service

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
) -> JobListResponse:
    items, total = job_service.list_job_details(
        page=page,
        page_size=page_size,
        status=status,
        job_type=job_type,
        keyword=keyword,
    )
    return JobListResponse(
        items=items,
        meta=PaginationMeta(page=page, page_size=page_size, total=total),
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    deleted = job_service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "deleted": True}
