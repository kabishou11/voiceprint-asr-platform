from fastapi import APIRouter, HTTPException

from ..schemas import (
    CreateTranscriptionRequest,
    CreateTranscriptionResponse,
    MeetingMinutesResponse,
    TranscriptResponse,
)
from ...services.job_service import job_service
from ...services.meeting_minutes import build_meeting_minutes

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


@router.post("", response_model=CreateTranscriptionResponse)
def create_transcription(payload: CreateTranscriptionRequest) -> CreateTranscriptionResponse:
    multi_speaker_requested = any(
        value is not None
        for value in (
            payload.diarization_model,
            payload.num_speakers,
            payload.min_speakers,
            payload.max_speakers,
        )
    )
    job_type = "multi_speaker_transcription" if multi_speaker_requested else "transcription"
    try:
        job = job_service.create_transcription_job(
            asset_name=payload.asset_name,
            job_type=job_type,
            diarization_model=payload.diarization_model,
            hotwords=payload.hotwords,
            language=payload.language,
            vad_enabled=payload.vad_enabled,
            itn=payload.itn,
            num_speakers=payload.num_speakers,
            min_speakers=payload.min_speakers,
            max_speakers=payload.max_speakers,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CreateTranscriptionResponse(job=job)


@router.get("/{job_id}", response_model=TranscriptResponse)
def get_transcription(job_id: str) -> TranscriptResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return TranscriptResponse(job=job, transcript=job.result)


@router.get("/{job_id}/minutes", response_model=MeetingMinutesResponse)
def get_meeting_minutes(job_id: str) -> MeetingMinutesResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        minutes = build_meeting_minutes(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MeetingMinutesResponse(
        job_id=job.job_id,
        title=minutes.title,
        summary=minutes.summary,
        key_points=minutes.key_points,
        action_items=minutes.action_items,
        speaker_stats=[
            {
                "speaker": item.speaker,
                "segment_count": item.segment_count,
                "duration_ms": item.duration_ms,
            }
            for item in minutes.speaker_stats
        ],
    )
