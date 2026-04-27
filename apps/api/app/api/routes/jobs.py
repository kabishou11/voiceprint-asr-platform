from fastapi import APIRouter, HTTPException, Query

from ..schemas import JobListResponse, PaginationMeta
from ...services.job_service import job_service

router = APIRouter(tags=["任务管理"])


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="获取任务列表（分页）",
    description="分页获取任务列表，支持按状态、类型、关键词过滤。关键词会匹配文件名和任务 ID。",
)
def list_jobs(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数，最大 200"),
    status: str | None = Query(default=None, description="按状态过滤：queued / running / succeeded / failed"),
    job_type: str | None = Query(default=None, description="按类型过滤：transcription / multi_speaker_transcription / voiceprint_enroll / voiceprint_verify / voiceprint_identify"),
    keyword: str | None = Query(default=None, description="关键词搜索，匹配文件名或任务 ID"),
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


@router.get(
    "/jobs/{job_id}",
    summary="获取单个任务详情",
    description="根据任务 ID 获取任务详情，包含状态、结果、错误信息等。",
)
def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.delete(
    "/jobs/{job_id}",
    summary="删除任务",
    description="根据任务 ID 删除任务记录。删除后不可恢复。",
)
def delete_job(job_id: str):
    deleted = job_service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"job_id": job_id, "deleted": True}
