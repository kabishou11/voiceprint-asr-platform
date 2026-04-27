from fastapi import APIRouter, File, HTTPException, UploadFile

from ..schemas import UploadAssetResponse
from ...services.asset_storage import asset_storage_service

router = APIRouter(prefix="/assets", tags=["资产管理"])


@router.post(
    '/upload',
    response_model=UploadAssetResponse,
    summary="上传音频文件",
    description="上传音频文件到服务端，返回 asset_name 供后续转写、声纹等接口使用。支持 wav / m4a / mp3 / flac 格式。",
)
def upload_asset(file: UploadFile = File(..., description="音频文件")) -> UploadAssetResponse:
    try:
        payload = asset_storage_service.save_upload(file.filename, file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadAssetResponse(**payload)
