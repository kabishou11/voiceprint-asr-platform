from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import httpx
from domain.schemas.transcript import JobDetail, Segment

from . import job_db
from ..core.config import get_settings


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
    mode: str
    model: str | None = None
    reasoning: str | None = None
    evidence: dict[str, list[dict[str, Any]]] | None = None


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
_LLM_CHUNK_CHAR_LIMIT = 12000


def meeting_minutes_supported(job: JobDetail) -> bool:
    return job.job_type in job_db.TRANSCRIPTION_JOB_TYPES


def serialize_minutes(minutes: MeetingMinutes) -> str:
    return json.dumps(
        {
            "title": minutes.title,
            "summary": minutes.summary,
            "key_points": minutes.key_points,
            "topics": minutes.topics,
            "decisions": minutes.decisions,
            "action_items": minutes.action_items,
            "risks": minutes.risks,
            "keywords": minutes.keywords,
            "speaker_stats": [
                {
                    "speaker": item.speaker,
                    "segment_count": item.segment_count,
                    "duration_ms": item.duration_ms,
                }
                for item in minutes.speaker_stats
            ],
            "markdown": minutes.markdown,
            "mode": minutes.mode,
            "model": minutes.model,
            "reasoning": minutes.reasoning,
            "evidence": minutes.evidence,
        },
        ensure_ascii=False,
    )


def deserialize_minutes(payload: str) -> MeetingMinutes:
    data = json.loads(payload)
    return MeetingMinutes(
        title=str(data["title"]),
        summary=str(data["summary"]),
        key_points=[str(item) for item in data.get("key_points") or []],
        topics=[str(item) for item in data.get("topics") or []],
        decisions=[str(item) for item in data.get("decisions") or []],
        action_items=[str(item) for item in data.get("action_items") or []],
        risks=[str(item) for item in data.get("risks") or []],
        keywords=[str(item) for item in data.get("keywords") or []],
        speaker_stats=[
            SpeakerMinuteStats(
                speaker=str(item["speaker"]),
                segment_count=int(item["segment_count"]),
                duration_ms=int(item["duration_ms"]),
            )
            for item in data.get("speaker_stats") or []
        ],
        markdown=str(data["markdown"]),
        mode=str(data["mode"]),
        model=str(data["model"]) if data.get("model") is not None else None,
        reasoning=str(data["reasoning"]) if data.get("reasoning") is not None else None,
        evidence=data.get("evidence") if isinstance(data.get("evidence"), dict) else None,
    )


def get_stored_minutes(job_id: str) -> MeetingMinutes | None:
    with job_db.session() as db:
        record = db.get(job_db.MinutesRecord, job_id)
        if record is None:
            return None
        return deserialize_minutes(record.payload)


def store_minutes(job_id: str, minutes: MeetingMinutes) -> MeetingMinutes:
    payload = serialize_minutes(minutes)
    with job_db.session() as db:
        record = db.get(job_db.MinutesRecord, job_id)
        if record is None:
            record = job_db.MinutesRecord(
                job_id=job_id,
                payload=payload,
                mode=minutes.mode,
                model=minutes.model,
            )
            db.add(record)
        else:
            record.payload = payload
            record.mode = minutes.mode
            record.model = minutes.model
        db.commit()
    return minutes


def generate_and_store_minutes(job: JobDetail, use_llm: bool) -> MeetingMinutes:
    minutes = build_llm_meeting_minutes(job) if use_llm else build_meeting_minutes(job)
    return store_minutes(job.job_id, minutes)


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
        for token in re.findall(r"[\w一-鿿]{2,}", sentence.lower()):
            if token not in _STOPWORDS:
                tokens[token] += 1

    def score(sentence: str) -> tuple[int, int]:
        words = re.findall(r"[\w一-鿿]{2,}", sentence.lower())
        lexical_score = sum(tokens[word] for word in words)
        return lexical_score, min(len(sentence), 120)

    return sorted(sentences, key=score, reverse=True)


def _extract_keywords(sentences: list[str], limit: int = 12) -> list[str]:
    tokens = Counter()
    for sentence in sentences:
        for token in re.findall(r"[\w一-鿿]{2,}", sentence.lower()):
            if token not in _STOPWORDS and not token.startswith("speaker_"):
                tokens[token] += 1
    return [token for token, _ in tokens.most_common(limit)]


def _select_by_keywords(sentences: list[str], keywords: tuple[str, ...], limit: int) -> list[str]:
    return [
        sentence
        for sentence in sentences
        if any(keyword in sentence for keyword in keywords)
    ][:limit]


def _build_speaker_stats(segments: list[Segment]) -> list[SpeakerMinuteStats]:
    speaker_durations: dict[str, int] = defaultdict(int)
    speaker_segments: dict[str, int] = defaultdict(int)
    for segment in segments:
        speaker = segment.speaker or "未标注说话人"
        speaker_segments[speaker] += 1
        speaker_durations[speaker] += max(0, segment.end_ms - segment.start_ms)

    return sorted(
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


def _segment_chunks_for_minutes(
    segments: list[Segment],
    *,
    max_chars: int = _LLM_CHUNK_CHAR_LIMIT,
) -> list[list[Segment]]:
    if not segments:
        return []
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    current_len = 0
    for segment in segments:
        segment_len = len(_segment_sentence(segment)) + 1
        if current and current_len + segment_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(segment)
        current_len += segment_len
    if current:
        chunks.append(current)
    return chunks


def _build_local_minutes_payload(segments: list[Segment], fallback_text: str = "") -> dict[str, Any]:
    source_sentences = [_segment_sentence(segment) for segment in segments]
    sentences = [item for sentence in source_sentences for item in _split_sentences(sentence)]
    if not sentences and fallback_text:
        sentences = _split_sentences(fallback_text)

    ranked = _rank_sentences(sentences)
    key_points = ranked[:6]
    return {
        "summary": " ".join(key_points[:3] or sentences[:3]) if sentences else "暂无足够文本生成会议纪要。",
        "key_points": key_points,
        "topics": [item.split(":", 1)[-1].strip() for item in ranked[:5]],
        "decisions": _select_by_keywords(sentences, _DECISION_KEYWORDS, 8),
        "action_items": _select_by_keywords(sentences, _ACTION_KEYWORDS, 8),
        "risks": _select_by_keywords(sentences, _RISK_KEYWORDS, 8),
        "keywords": _extract_keywords(sentences),
    }


def _build_minutes_evidence(
    segments: list[Segment],
    *,
    decisions: list[str],
    action_items: list[str],
    risks: list[str],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "decisions": [_evidence_for_item(item, segments) for item in decisions],
        "action_items": [_evidence_for_item(item, segments) for item in action_items],
        "risks": [_evidence_for_item(item, segments) for item in risks],
    }


def _evidence_for_item(item: str, segments: list[Segment]) -> dict[str, Any]:
    best_segment = _best_evidence_segment(item, segments)
    if best_segment is None:
        return {"item": item, "matched": False}
    return {
        "item": item,
        "matched": True,
        "speaker": best_segment.speaker or "未标注说话人",
        "start_ms": best_segment.start_ms,
        "end_ms": best_segment.end_ms,
        "text": best_segment.text,
    }


def _best_evidence_segment(item: str, segments: list[Segment]) -> Segment | None:
    normalized_item = _normalize_evidence_text(item)
    if not normalized_item:
        return None
    best: tuple[float, Segment] | None = None
    for segment in segments:
        normalized_segment = _normalize_evidence_text(segment.text)
        if not normalized_segment:
            continue
        score = _evidence_score(normalized_item, normalized_segment)
        if best is None or score > best[0]:
            best = (score, segment)
    if best is None or best[0] < 0.45:
        return None
    return best[1]


def _evidence_score(item: str, segment: str) -> float:
    if item in segment:
        return 1.0
    tokens = [
        token
        for token in re.findall(r"[\w一-鿿]{2,}", item)
        if len(token) >= 2
    ]
    if not tokens:
        return 0.0
    matched = sum(1 for token in tokens if token in segment)
    return matched / len(tokens)


def _normalize_evidence_text(text: str | None) -> str:
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"^[^:：]{1,24}[:：]\s*", "", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[，。！？；：、“”‘’,.!?;:~\-—_\(\)\[\]{}<>《》/\\|]", "", cleaned)
    return cleaned


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
    evidence: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    def section(name: str, items: list[str]) -> list[str]:
        if not items:
            return [f"## {name}", "- 暂无"]
        return [f"## {name}", *[f"- {item}" for item in items]]

    speaker_lines = [
        f"- {item.speaker}: {item.segment_count} 段，{item.duration_ms / 1000:.1f} 秒"
        for item in speaker_stats
    ] or ["- 暂无"]
    evidence_lines = _format_evidence_lines(evidence)

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
        "",
        "## 证据引用",
        *evidence_lines,
    ]
    return "\n".join(lines)


def _format_evidence_lines(evidence: dict[str, list[dict[str, Any]]] | None) -> list[str]:
    if not evidence:
        return ["- 暂无"]
    labels = {
        "decisions": "决策",
        "action_items": "行动项",
        "risks": "风险",
    }
    lines: list[str] = []
    for key, label in labels.items():
        items = evidence.get(key) or []
        lines.append(f"### {label}")
        if not items:
            lines.append("- 暂无")
            continue
        for item in items:
            if not item.get("matched"):
                lines.append(f"- {item.get('item', '')}（未匹配到原文证据）")
                continue
            lines.append(
                f"- {item.get('item', '')} -> {item.get('speaker')} "
                f"[{item.get('start_ms')}ms-{item.get('end_ms')}ms]"
            )
    return lines


def _transcript_payload(job: JobDetail) -> str:
    if job.result is None:
        return ""
    if job.result.segments:
        lines = []
        for segment in job.result.segments:
            speaker = segment.speaker or "未标注说话人"
            lines.append(
                f"[{segment.start_ms}-{segment.end_ms}ms] {speaker}: {segment.text}"
            )
        return "\n".join(lines)
    return job.result.text


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.S)
        parsed = json.loads(match.group(0)) if match else {}
    return parsed if isinstance(parsed, dict) else {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _build_llm_prompt(job: JobDetail, transcript: str, *, chunk_label: str | None = None) -> list[dict[str, str]]:
    label = f"{chunk_label}\n" if chunk_label else ""
    return [
        {
            "role": "system",
            "content": (
                "你是专业会议纪要助手。只输出 JSON，不要输出 Markdown fence。"
                "字段必须包含 summary,key_points,topics,decisions,action_items,risks,keywords。"
                "每个数组字段最多 8 条，中文表达，保留 Speaker 信息但不要编造事实。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"任务标题：{job.asset_name or job.job_id}\n"
                f"{label}"
                "请基于以下带时间戳转写生成会议纪要：\n\n"
                f"{transcript}"
            ),
        },
    ]


def _build_llm_reduce_prompt(job: JobDetail, chunk_payload: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是专业会议纪要归并助手。只输出 JSON，不要输出 Markdown fence。"
                "字段必须包含 summary,key_points,topics,decisions,action_items,risks,keywords。"
                "请合并去重，保留跨段出现的 Speaker 信息，不要编造事实。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"任务标题：{job.asset_name or job.job_id}\n"
                "下面是同一场长会议按时间顺序生成的分块纪要，请归并为最终会议纪要：\n\n"
                f"{chunk_payload}"
            ),
        },
    ]


def _call_llm_minutes(settings, messages: list[dict[str, str]]) -> tuple[dict[str, Any], str | None]:
    url = settings.minutes_llm_base_url.rstrip("/") + "/chat/completions"
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.minutes_llm_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.minutes_llm_model,
            "messages": messages,
            "reasoning_split": settings.minutes_llm_reasoning_split,
            "stream": False,
            "temperature": 0.2,
        },
        timeout=settings.minutes_llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = str(message.get("content") or "")
    reasoning = ""
    for detail in message.get("reasoning_details") or []:
        if isinstance(detail, dict) and "text" in detail:
            reasoning += str(detail["text"])

    return _parse_json_object(content), reasoning or None


def _chunk_transcript_payload(transcript: str, *, max_chars: int = _LLM_CHUNK_CHAR_LIMIT) -> list[str]:
    if len(transcript) <= max_chars:
        return [transcript]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in transcript.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if line_len > max_chars:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(line), max_chars):
                chunks.append(line[start:start + max_chars])
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return [chunk for chunk in chunks if chunk.strip()]


def _merge_minutes_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    def collect(key: str, limit: int = 12) -> list[str]:
        seen = set()
        items: list[str] = []
        for payload in payloads:
            for item in _as_list(payload.get(key)):
                if item not in seen:
                    seen.add(item)
                    items.append(item)
                if len(items) >= limit:
                    return items
        return items

    summaries = [str(payload.get("summary")).strip() for payload in payloads if str(payload.get("summary") or "").strip()]
    return {
        "summary": " ".join(summaries[:3]),
        "key_points": collect("key_points"),
        "topics": collect("topics"),
        "decisions": collect("decisions"),
        "action_items": collect("action_items"),
        "risks": collect("risks"),
        "keywords": collect("keywords", limit=16),
    }


def build_llm_meeting_minutes(job: JobDetail) -> MeetingMinutes:
    settings = get_settings()
    if not settings.minutes_llm_api_key:
        raise RuntimeError("未配置 MINUTES_LLM_API_KEY，无法调用会议纪要模型")

    baseline = build_meeting_minutes(job)
    transcript = _transcript_payload(job)
    chunks = _chunk_transcript_payload(transcript)
    parsed_chunks: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        parsed, reasoning = _call_llm_minutes(
            settings,
            _build_llm_prompt(
                job,
                chunk,
                chunk_label=f"这是第 {index}/{len(chunks)} 个时间顺序分块。",
            ),
        )
        parsed_chunks.append(parsed)
        if reasoning:
            reasoning_parts.append(reasoning)

    if len(parsed_chunks) > 1:
        merged_payload = _merge_minutes_payloads(parsed_chunks)
        reduce_payload = json.dumps(
            {
                "chunks": parsed_chunks,
                "merged_draft": merged_payload,
            },
            ensure_ascii=False,
        )
        parsed, reasoning = _call_llm_minutes(settings, _build_llm_reduce_prompt(job, reduce_payload))
        if reasoning:
            reasoning_parts.append(reasoning)
        if not parsed:
            parsed = merged_payload
    else:
        parsed = parsed_chunks[0] if parsed_chunks else {}

    title = job.asset_name or f"会议纪要 {job.job_id}"
    summary = str(parsed.get("summary") or baseline.summary)
    key_points = _as_list(parsed.get("key_points")) or baseline.key_points
    topics = _as_list(parsed.get("topics")) or baseline.topics
    decisions = _as_list(parsed.get("decisions")) or baseline.decisions
    action_items = _as_list(parsed.get("action_items")) or baseline.action_items
    risks = _as_list(parsed.get("risks")) or baseline.risks
    keywords = _as_list(parsed.get("keywords")) or baseline.keywords
    segments = job.result.segments if job.result is not None else []
    evidence = _build_minutes_evidence(
        segments,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
    )

    return MeetingMinutes(
        title=title,
        summary=summary,
        key_points=key_points,
        topics=topics,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
        keywords=keywords,
        speaker_stats=baseline.speaker_stats,
        markdown=_build_markdown(
            title=title,
            summary=summary,
            key_points=key_points,
            topics=topics,
            decisions=decisions,
            action_items=action_items,
            risks=risks,
            keywords=keywords,
            speaker_stats=baseline.speaker_stats,
            evidence=evidence,
        ),
        mode="llm",
        model=settings.minutes_llm_model,
        reasoning="\n".join(reasoning_parts) or None,
        evidence=evidence,
    )


def build_meeting_minutes(job: JobDetail) -> MeetingMinutes:
    if job.result is None:
        raise ValueError("任务尚无可生成会议纪要的转写结果")

    segments = job.result.segments
    if segments:
        payloads = [
            _build_local_minutes_payload(chunk)
            for chunk in _segment_chunks_for_minutes(segments)
        ]
    else:
        payloads = [
            _build_local_minutes_payload([], chunk)
            for chunk in _chunk_transcript_payload(job.result.text)
        ]
    payload = _merge_minutes_payloads(payloads) if len(payloads) > 1 else (payloads[0] if payloads else {})

    summary = str(payload.get("summary") or "暂无足够文本生成会议纪要。")
    key_points = _as_list(payload.get("key_points"))
    topics = _as_list(payload.get("topics"))
    decisions = _as_list(payload.get("decisions"))
    action_items = _as_list(payload.get("action_items"))
    risks = _as_list(payload.get("risks"))
    keywords = _as_list(payload.get("keywords"))
    speaker_stats = _build_speaker_stats(segments)
    title = job.asset_name or f"会议纪要 {job.job_id}"
    evidence = _build_minutes_evidence(
        segments,
        decisions=decisions,
        action_items=action_items,
        risks=risks,
    )

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
            evidence=evidence,
        ),
        mode="local",
        evidence=evidence,
    )
