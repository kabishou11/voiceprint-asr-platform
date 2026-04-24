from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from domain.schemas.transcript import JobDetail, Segment


@dataclass(frozen=True)
class SpeakerMinuteStats:
    speaker: str
    segment_count: int
    duration_ms: int


@dataclass(frozen=True)
class MeetingMinutes:
    title: str
    summary: str
    key_points: list[str]
    action_items: list[str]
    speaker_stats: list[SpeakerMinuteStats]


_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?])\s*|[\n\r]+")
_ACTION_KEYWORDS = (
    "需要",
    "负责",
    "跟进",
    "确认",
    "安排",
    "推进",
    "完成",
    "下次",
    "todo",
    "TODO",
)


def _split_sentences(text: str) -> list[str]:
    sentences = [item.strip() for item in _SENTENCE_SPLIT_PATTERN.split(text) if item.strip()]
    return [sentence for sentence in sentences if len(sentence) >= 2]


def _segment_sentence(segment: Segment) -> str:
    speaker = segment.speaker or "未标注说话人"
    text = segment.text.strip()
    if not text:
        return ""
    return f"{speaker}: {text}"


def _rank_sentences(sentences: list[str]) -> list[str]:
    tokens = Counter()
    for sentence in sentences:
        for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", sentence.lower()):
            if token not in {"这个", "就是", "然后", "我们", "你们", "他们", "进行", "一个"}:
                tokens[token] += 1

    def score(sentence: str) -> tuple[int, int]:
        words = re.findall(r"[\w\u4e00-\u9fff]{2,}", sentence.lower())
        lexical_score = sum(tokens[word] for word in words)
        return lexical_score, min(len(sentence), 120)

    return sorted(sentences, key=score, reverse=True)


def build_meeting_minutes(job: JobDetail) -> MeetingMinutes:
    if job.result is None:
        raise ValueError("任务尚无可生成会议纪要的转写结果")

    segments = job.result.segments
    source_sentences = [_segment_sentence(segment) for segment in segments]
    sentences = [item for sentence in source_sentences for item in _split_sentences(sentence)]
    if not sentences and job.result.text:
        sentences = _split_sentences(job.result.text)

    ranked = _rank_sentences(sentences)
    key_points = ranked[:6]
    action_items = [
        sentence
        for sentence in sentences
        if any(keyword in sentence for keyword in _ACTION_KEYWORDS)
    ][:8]

    speaker_durations: dict[str, int] = defaultdict(int)
    speaker_segments: dict[str, int] = defaultdict(int)
    for segment in segments:
        speaker = segment.speaker or "未标注说话人"
        speaker_segments[speaker] += 1
        speaker_durations[speaker] += max(0, segment.end_ms - segment.start_ms)

    speaker_stats = sorted(
        [
            SpeakerMinuteStats(
                speaker=speaker,
                segment_count=speaker_segments[speaker],
                duration_ms=speaker_durations[speaker],
            )
            for speaker in speaker_segments
        ],
        key=lambda item: item.duration_ms,
        reverse=True,
    )

    summary_seed = key_points[:3] or sentences[:3]
    summary = " ".join(summary_seed) if summary_seed else "暂无足够文本生成会议纪要。"

    return MeetingMinutes(
        title=job.asset_name or f"会议纪要 {job.job_id}",
        summary=summary,
        key_points=key_points,
        action_items=action_items,
        speaker_stats=speaker_stats,
    )
