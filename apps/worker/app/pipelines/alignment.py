from __future__ import annotations

from domain.schemas.transcript import Segment, TranscriptResult


def align_transcript_with_speakers(
    transcript: TranscriptResult,
    diarization_segments: list[Segment],
) -> TranscriptResult:
    if not diarization_segments:
        return transcript
    merged: list[Segment] = []
    for index, segment in enumerate(transcript.segments):
        speaker = diarization_segments[min(index, len(diarization_segments) - 1)].speaker
        merged.append(segment.model_copy(update={"speaker": speaker}))
    return TranscriptResult(text=transcript.text, language=transcript.language, segments=merged)
