from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import assets, diarization, jobs, system, transcription, voiceprints
from .core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(system.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(transcription.router, prefix="/api/v1")
app.include_router(voiceprints.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(diarization.router, prefix="/api/v1")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ok"}
