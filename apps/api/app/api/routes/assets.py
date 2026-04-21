from fastapi import APIRouter, File, HTTPException, UploadFile

from ..schemas import UploadAssetResponse
from ...services.asset_storage import asset_storage_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post('/upload', response_model=UploadAssetResponse)
def upload_asset(file: UploadFile = File(...)) -> UploadAssetResponse:
    try:
        payload = asset_storage_service.save_upload(file.filename, file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadAssetResponse(**payload)
