from fastapi import APIRouter, HTTPException

from ...services.job_service import job_service
from ...services import job_db
from ...services.meeting_minutes import (
    generate_and_store_minutes,
    get_stored_minutes,
    meeting_minutes_supported,
)
from ..schemas import (
    CreateTranscriptionRequest,
    CreateTranscriptionResponse,
    MeetingMinutesResponse,
    TranscriptResponse,
)

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])


def _assert_minutes_supported(job) -> None:
    if not meeting_minutes_supported(job):
        raise HTTPException(status_code=409, detail="仅转写任务支持会议纪要")


def _minutes_response(job_id: str, minutes) -> MeetingMinutesResponse:
    return MeetingMinutesResponse(
        job_id=job_id,
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
            asr_model=payload.asr_model,
            diarization_model=payload.diarization_model,
            hotwords=payload.hotwords,
            language=payload.language,
            vad_enabled=payload.vad_enabled,
            itn=payload.itn,
            voiceprint_scope_mode=payload.voiceprint_scope_mode,
            voiceprint_group_id=payload.voiceprint_group_id,
            voiceprint_profile_ids=payload.voiceprint_profile_ids,
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
    _assert_minutes_supported(job)

    minutes = get_stored_minutes(job_id)
    if minutes is None:
        raise HTTPException(status_code=404, detail="尚未生成会议纪要，请先调用 POST 生成。")
    return _minutes_response(job.job_id, minutes)


@router.post("/{job_id}/minutes", response_model=MeetingMinutesResponse)
def generate_meeting_minutes(job_id: str, use_llm: bool = True) -> MeetingMinutesResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    _assert_minutes_supported(job)

    try:
        minutes = generate_and_store_minutes(job, use_llm=use_llm)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"会议纪要模型调用失败: {exc}") from exc
    return _minutes_response(job.job_id, minutes)


@router.get("/{job_id}/speaker-aliases")
def get_speaker_aliases(job_id: str):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    with job_db.session() as db:
        records = (
            db.query(job_db.SpeakerAliasRecord)
            .filter(job_db.SpeakerAliasRecord.job_id == job_id)
            .all()
        )
        return {
            "job_id": job_id,
            "aliases": {record.speaker_key: record.display_name for record in records},
        }


@router.put("/{job_id}/speaker-aliases")
def upsert_speaker_aliases(job_id: str, aliases: dict[str, str]):
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    with job_db.session() as db:
        for speaker_key, display_name in aliases.items():
            existing = db.get(job_db.SpeakerAliasRecord, (job_id, speaker_key))
            if existing is None:
                db.add(job_db.SpeakerAliasRecord(
                    job_id=job_id,
                    speaker_key=speaker_key,
                    display_name=display_name,
                ))
            else:
                existing.display_name = display_name
        db.commit()
    return {"job_id": job_id, "updated": len(aliases)}
