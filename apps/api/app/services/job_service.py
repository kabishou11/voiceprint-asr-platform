from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from domain.schemas.transcript import JobDetail, JobSummary, Segment, TranscriptResult
from model_adapters import resolve_audio_asset_path

from .model_runtime import get_model_registry


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, JobDetail] = {}
        demo_job = JobDetail(
            job_id=str(uuid4()),
            job_type="transcription",
            status="succeeded",
            asset_name="sample-meeting.wav",
            result=TranscriptResult(
                text="欢迎使用 voiceprint-asr-platform。",
                language="zh",
                segments=[
                    Segment(start_ms=0, end_ms=2300, text="欢迎使用", speaker="SPEAKER_00"),
                    Segment(start_ms=2300, end_ms=5200, text="voiceprint-asr-platform。", speaker="SPEAKER_00"),
                ],
            ),
        )
        self._jobs[demo_job.job_id] = demo_job

    def list_jobs(self) -> list[JobSummary]:
        return [JobSummary(**job.model_dump(exclude={"result", "error_message"})) for job in self._jobs.values()]

    def get_job(self, job_id: str) -> JobDetail | None:
        return self._jobs.get(job_id)

    def create_transcription_job(self, asset_name: str, job_type: str = "transcription") -> JobDetail:
        registry = get_model_registry()
        result: TranscriptResult | None = None
        if job_type == "transcription":
            adapter = registry.get_asr("funasr-nano")
            result = adapter.transcribe(asset=self._build_asset(asset_name))
        elif job_type == "multi_speaker_transcription":
            asr_adapter = registry.get_asr("funasr-nano")
            diarization_adapter = registry.get_diarization("3dspeaker-diarization")
            asset = self._build_asset(asset_name)
            transcript = asr_adapter.transcribe(asset=asset)
            diarization_segments = diarization_adapter.diarize(asset=asset)
            merged_segments = self._merge_segments(transcript.segments, diarization_segments)
            result = TranscriptResult(text=transcript.text, language=transcript.language, segments=merged_segments)
        job = JobDetail(
            job_id=str(uuid4()),
            job_type=job_type,
            status="succeeded" if result is not None else "queued",
            asset_name=asset_name,
            result=result,
        )
        self._jobs[job.job_id] = job
        return job

    def seed_jobs(self, jobs: Iterable[JobDetail]) -> None:
        for job in jobs:
            self._jobs[job.job_id] = job

    def _build_asset(self, asset_name: str):
        from model_adapters import AudioAsset

        return AudioAsset(path=resolve_audio_asset_path(asset_name))

    def _merge_segments(self, transcript_segments: list[Segment], speaker_segments: list[Segment]) -> list[Segment]:
        if not transcript_segments:
            return speaker_segments
        if not speaker_segments:
            return transcript_segments
        merged: list[Segment] = []
        for index, segment in enumerate(transcript_segments):
            speaker = speaker_segments[min(index, len(speaker_segments) - 1)].speaker
            merged.append(segment.model_copy(update={"speaker": speaker}))
        return merged


job_service = JobService()
