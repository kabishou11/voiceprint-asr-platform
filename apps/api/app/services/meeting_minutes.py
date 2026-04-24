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
    topics: list[str]
    decisions: list[str]
    action_items: list[str]
    risks: list[str]
    keywords: list[str]
    speaker_stats: list[SpeakerMinuteStats]
    markdown: str


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
_DECISION_KEYWORDS = ("决定", "确认", "结论", "同意", "通过", "定下来", "方案")
_RISK_KEYWORDS = ("风险", "问题", "阻塞", "延期", "不确定", "依赖", "缺少", "失败", "bug", "异常")
_STOPWORDS = {
    "这个",
    "就是",
    "然后",
    "我们",
    "你们",
    "他们",
    "进行",
    "一个",
    "可以",
    "现在",
    "如果",
    "因为",
    "所以",
    "还是",
    "没有",
}


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
            if token not in _STOPWORDS:
                tokens[token] += 1

    def score(sentence: str) -> tuple[int, int]:
        words = re.findall(r"[\w\u4e00-\u9fff]{2,}", sentence.lower())
        lexical_score = sum(tokens[word] for word in words)
        return lexical_score, min(len(sentence), 120)

    return sorted(sentences, key=score, reverse=True)


def _extract_keywords(sentences: list[str], limit: int = 12) -> list[str]:
    tokens = Counter()
    for sentence in sentences:
        for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", sentence.lower()):
            if token not in _STOPWORDS and not token.startswith("speaker_"):
                tokens[token] += 1
    return [token for token, _ in tokens.most_common(limit)]


def _select_by_keywords(sentences: list[str], keywords: tuple[str, ...], limit: int) -> list[str]:
    return [sentence for sentence in sentences if any(keyword in sentence for keyword in keywords)][:limit]


def _build_markdown(
    *,
    title: str,
    summary: str,
    key_points: list[str],
    topics: list[str],
    decisions: list[str],
    action_items: list[str],
    risks: list[str],
    keywords: list[str],
    speaker_stats: list[SpeakerMinuteStats],
) -> str:
    def section(name: str, items: list[str]) -> list[str]:
        if not items:
            return [f"## {name}", "- 暂无"]
        return [f"## {name}", *[f"- {item}" for item in items]]

    speaker_lines = [
        f"- {item.speaker}: {item.segment_count} 段，{item.duration_ms / 1000:.1f} 秒"
        for item in speaker_stats
    ] or ["- 暂无"]

    lines = [
        f"# {title}",
        "",
        "## 摘要",
        summary or "暂无",
        "",
        *section("核心要点", key_points),
        "",
        *section("议题", topics),
        "",
        *section("决策", decisions),
        "",
        *section("行动项", action_items),
        "",
        *section("风险与阻塞", risks),
        "",
        "## 关键词",
        ", ".join(keywords) if keywords else "暂无",
        "",
        "## Speaker 统计",
        *speaker_lines,
    ]
    return "\n".join(lines)


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
    topics = [item.split(":", 1)[-1].strip() for item in ranked[:5]]
    decisions = _select_by_keywords(sentences, _DECISION_KEYWORDS, 8)
    action_items = _select_by_keywords(sentences, _ACTION_KEYWORDS, 8)
    risks = _select_by_keywords(sentences, _RISK_KEYWORDS, 8)
    keywords = _extract_keywords(sentences)

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
    title = job.asset_name or f"会议纪要 {job.job_id}"

    return MeetingMinutes(
        title=title,
        summary=summary,
        key_points=key_points,
        topics=topics,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
        keywords=keywords,
        speaker_stats=speaker_stats,
        markdown=_build_markdown(
            title=title,
            summary=summary,
            key_points=key_points,
            topics=topics,
            decisions=decisions,
            action_items=action_items,
            risks=risks,
            keywords=keywords,
            speaker_stats=speaker_stats,
        ),
    )
