from fastapi import APIRouter, HTTPException

from ..schemas import (
    CreateTranscriptionRequest,
    CreateTranscriptionResponse,
    TranscriptResponse,
)
from ...services.job_service import job_service

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


@router.post("", response_model=CreateTranscriptionResponse)
def create_transcription(payload: CreateTranscriptionRequest) -> CreateTranscriptionResponse:
    job_type = "multi_speaker_transcription" if payload.diarization_model else "transcription"
    job = job_service.create_transcription_job(
        asset_name=payload.asset_name,
        job_type=job_type,
        hotwords=payload.hotwords,
        language=payload.language,
        vad_enabled=payload.vad_enabled,
        itn=payload.itn,
    )
    return CreateTranscriptionResponse(job=job)


@router.get("/{job_id}", response_model=TranscriptResponse)
def get_transcription(job_id: str) -> TranscriptResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return TranscriptResponse(job=job, transcript=job.result)
