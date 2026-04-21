from fastapi import APIRouter

from ..schemas import HealthResponse
from ...core.config import get_settings
from ...services.model_registry import ModelRegistryService

router = APIRouter(tags=["system"])
registry = ModelRegistryService()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app_name=settings.app_name)


@router.get("/models")
def list_models():
    return {"items": registry.list_models()}
