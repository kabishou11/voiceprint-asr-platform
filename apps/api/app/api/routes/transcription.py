from fastapi import APIRouter, HTTPException

from ...services.job_service import job_service
from ...services.meeting_minutes import build_llm_meeting_minutes, build_meeting_minutes
from ..schemas import (
    CreateTranscriptionRequest,
    CreateTranscriptionResponse,
    MeetingMinutesResponse,
    TranscriptResponse,
)

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
        topics=minutes.topics,
        decisions=minutes.decisions,
        action_items=minutes.action_items,
        risks=minutes.risks,
        keywords=minutes.keywords,
        speaker_stats=[
            {
                "speaker": item.speaker,
                "segment_count": item.segment_count,
                "duration_ms": item.duration_ms,
            }
            for item in minutes.speaker_stats
        ],
        markdown=minutes.markdown,
        mode=minutes.mode,
        model=minutes.model,
        reasoning=minutes.reasoning,
    )


@router.post("/{job_id}/minutes", response_model=MeetingMinutesResponse)
def generate_meeting_minutes(job_id: str, use_llm: bool = True) -> MeetingMinutesResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        minutes = build_llm_meeting_minutes(job) if use_llm else build_meeting_minutes(job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"会议纪要模型调用失败: {exc}") from exc
    return MeetingMinutesResponse(
        job_id=job.job_id,
        title=minutes.title,
        summary=minutes.summary,
        key_points=minutes.key_points,
        topics=minutes.topics,
        decisions=minutes.decisions,
        action_items=minutes.action_items,
        risks=minutes.risks,
        keywords=minutes.keywords,
        speaker_stats=[
            {
                "speaker": item.speaker,
                "segment_count": item.segment_count,
                "duration_ms": item.duration_ms,
            }
            for item in minutes.speaker_stats
        ],
        markdown=minutes.markdown,
        mode=minutes.mode,
        model=minutes.model,
        reasoning=minutes.reasoning,
    )
