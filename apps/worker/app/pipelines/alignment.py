from __future__ import annotations

import re

from domain.schemas.transcript import Segment, TranscriptResult


def canonicalize_speaker_labels(segments: list[Segment]) -> list[Segment]:
    """按首次出现顺序规范化 speaker 标签。

    聚类模型输出的 speaker id 天然无序，同一段会议的首位说话人可能是
    SPEAKER_02。这里统一重排为 SPEAKER_00、SPEAKER_01...，让导出、
    metadata 和声纹回写更稳定。
    """
    mapping: dict[str, str] = {}
    canonicalized: list[Segment] = []
    for segment in sorted(segments, key=lambda item: (item.start_ms, item.end_ms, item.speaker or "")):
        speaker = segment.speaker
        if speaker is None:
            canonicalized.append(segment)
            continue
        if speaker not in mapping:
            mapping[speaker] = f"SPEAKER_{len(mapping):02d}"
        canonicalized.append(segment.model_copy(update={"speaker": mapping[speaker]}))
    return canonicalized


def align_transcript_with_speakers(
    transcript: TranscriptResult,
    diarization_segments: list[Segment],
) -> TranscriptResult:
    """将转写结果与说话人分离结果对齐。

    对齐策略：
    1. 如果分段落有 speaker 信息（来自 ASR 内置说话人分离），直接使用
    2. 否则，根据时间重叠度将每个转写段落分配给最匹配的说话人段落
    3. 处理孤立说话人段（无对应文本）和孤立文本段（无说话人标签）

    Args:
        transcript: ASR 转写结果（包含时间戳段落）
        diarization_segments: 说话人分离结果（每段有 speaker 标签）

    Returns:
        合并后的转写结果（每段包含 speaker 标签）
    """
    exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)

    if not exclusive_segments:
        return TranscriptResult(
            text=transcript.text,
            language=transcript.language,
            segments=merge_short_segments(transcript.segments),
        )

    # 方案 1：转写段落已有 speaker 信息（如 SenseVoice 内置分离）
    if transcript.segments and all(seg.speaker is not None for seg in transcript.segments):
        return TranscriptResult(
            text=transcript.text,
            language=transcript.language,
            segments=merge_short_segments(transcript.segments),
        )

    # 方案 2：基于 diarization 时间轴做二次切分
    aligned: list[Segment] = []
    for seg in transcript.segments:
        if seg.speaker is not None:
            aligned.append(seg)
            continue
        aligned.extend(_split_segment_by_speakers(seg, exclusive_segments))

    return TranscriptResult(
        text=transcript.text,
        language=transcript.language,
        segments=merge_short_segments(aligned),
    )


def build_exclusive_speaker_timeline(diarization_segments: list[Segment]) -> list[Segment]:
    """将可能重叠的 diarization 段压成无重叠时间轴。

    这是对 pyannote `exclusive speaker diarization` 思路的轻量对齐版本：
    - 同 speaker 相邻/重叠段直接合并
    - 不同 speaker 重叠时按中点裁边，生成单说话人时间轴
    """
    if not diarization_segments:
        return []

    ordered = sorted(
        [
            segment.model_copy(update={"text": ""})
            for segment in diarization_segments
            if segment.end_ms > segment.start_ms
        ],
        key=lambda item: (item.start_ms, item.end_ms, item.speaker or ""),
    )
    if not ordered:
        return []

    exclusive: list[Segment] = [ordered[0]]
    for current in ordered[1:]:
        previous = exclusive[-1]
        if current.speaker == previous.speaker and current.start_ms <= previous.end_ms:
            exclusive[-1] = previous.model_copy(
                update={
                    "end_ms": max(previous.end_ms, current.end_ms),
                    "confidence": _max_confidence(previous.confidence, current.confidence),
                }
            )
            continue

        if current.start_ms < previous.end_ms:
            pivot = max(previous.start_ms, min(current.end_ms, round((previous.end_ms + current.start_ms) / 2)))
            exclusive[-1] = previous.model_copy(update={"end_ms": max(previous.start_ms, pivot)})
            current = current.model_copy(update={"start_ms": max(pivot, current.start_ms)})

        if current.end_ms <= current.start_ms:
            continue

        if current.speaker == exclusive[-1].speaker and current.start_ms <= exclusive[-1].end_ms:
            merged = exclusive[-1]
            exclusive[-1] = merged.model_copy(
                update={
                    "end_ms": max(merged.end_ms, current.end_ms),
                    "confidence": _max_confidence(merged.confidence, current.confidence),
                }
            )
            continue
        exclusive.append(current)

    return [segment for segment in exclusive if segment.end_ms > segment.start_ms]


def build_display_speaker_timeline(
    aligned_segments: list[Segment],
    fallback_segments: list[Segment] | None = None,
    *,
    max_gap_ms: int = 500,
    min_duration_ms: int = 1000,
) -> list[Segment]:
    """构建面向展示的稳定 speaker 时间线。

    display timeline 只服务任务页和可读导出：
    - 优先使用已经对齐到文本的 segments，保留更真实的说话切换感知
    - 对极短段和短间隙做保守压缩
    - 不反向修改 regular / exclusive 原始时间轴
    """
    source = [
        segment.model_copy(update={"text": ""})
        for segment in (aligned_segments or fallback_segments or [])
        if segment.end_ms > segment.start_ms
    ]
    if not source:
        return []

    ordered = sorted(source, key=lambda item: (item.start_ms, item.end_ms, item.speaker or ""))
    merged: list[Segment] = [ordered[0]]
    for segment in ordered[1:]:
        previous = merged[-1]
        gap_ms = segment.start_ms - previous.end_ms
        if (
            previous.speaker == segment.speaker
            and 0 <= gap_ms <= max_gap_ms
        ):
            merged[-1] = previous.model_copy(
                update={
                    "end_ms": max(previous.end_ms, segment.end_ms),
                    "confidence": _max_confidence(previous.confidence, segment.confidence),
                }
            )
            continue
        merged.append(segment)

    collapsed: list[Segment] = [merged[0]]
    index = 1
    while index < len(merged):
        current = merged[index]
        duration_ms = current.end_ms - current.start_ms
        previous = collapsed[-1]
        next_segment = merged[index + 1] if index + 1 < len(merged) else None
        if (
            duration_ms <= min_duration_ms
            and previous.speaker is not None
            and next_segment is not None
            and previous.speaker == next_segment.speaker
        ):
            collapsed[-1] = previous.model_copy(
                update={
                    "end_ms": next_segment.end_ms,
                    "confidence": _max_confidence(previous.confidence, next_segment.confidence),
                }
            )
            index += 2
            continue
        if (
            duration_ms <= min_duration_ms
            and previous.speaker == current.speaker
            and current.start_ms - previous.end_ms <= max_gap_ms
        ):
            collapsed[-1] = previous.model_copy(
                update={
                    "end_ms": max(previous.end_ms, current.end_ms),
                    "confidence": _max_confidence(previous.confidence, current.confidence),
                }
            )
            index += 1
            continue
        collapsed.append(current)
        index += 1

    return [segment for segment in collapsed if segment.end_ms > segment.start_ms]


def _split_segment_by_speakers(seg: Segment, diar_segments: list[Segment]) -> list[Segment]:
    seg_start, seg_end = seg.start_ms, seg.end_ms
    if seg_end <= seg_start:
        return [seg.model_copy(update={"speaker": _nearest_speaker(seg_start, diar_segments) or "SPEAKER_00"})]

    overlaps = [
        diar_seg
        for diar_seg in diar_segments
        if diar_seg.end_ms > seg_start and diar_seg.start_ms < seg_end
    ]
    if not overlaps:
        return [seg.model_copy(update={"speaker": _nearest_speaker(seg_start, diar_segments) or "SPEAKER_00"})]

    boundaries = {seg_start, seg_end}
    for diar_seg in overlaps:
        boundaries.add(max(seg_start, diar_seg.start_ms))
        boundaries.add(min(seg_end, diar_seg.end_ms))
    ordered = sorted(boundaries)
    if len(ordered) <= 2:
        best = _best_overlap_speaker(seg_start, seg_end, overlaps)
        return [seg.model_copy(update={"speaker": best or "SPEAKER_00"})]

    intervals = []
    for left, right in zip(ordered, ordered[1:]):
        if right <= left:
            continue
        speaker = _best_overlap_speaker(left, right, overlaps)
        if speaker is None:
            speaker = _nearest_speaker(left, diar_segments) or "SPEAKER_00"
        intervals.append((left, right, speaker))

    sentence_aligned = _split_text_by_sentence_units(seg, intervals)
    if sentence_aligned:
        return sentence_aligned

    pieces: list[Segment] = []
    total_duration = max(1, seg_end - seg_start)
    text = seg.text or ""
    consumed = 0
    for left, right, speaker in intervals:
        piece_duration = right - left
        start_idx = round(consumed / total_duration * len(text))
        consumed += piece_duration
        end_idx = round(consumed / total_duration * len(text))
        piece_text = text[start_idx:end_idx].strip()
        pieces.append(
            Segment(
                start_ms=left,
                end_ms=right,
                text=piece_text,
                speaker=speaker,
                confidence=seg.confidence,
            )
        )

    return [piece for piece in pieces if piece.end_ms > piece.start_ms]


def _split_text_by_sentence_units(seg: Segment, intervals: list[tuple[int, int, str]]) -> list[Segment]:
    text = _cleanup_segment_text(seg.text)
    if not text or len(intervals) <= 1:
        return []
    units = [item.strip() for item in re.split(r"(?<=[。！？!?；;，,])", text) if item.strip()]
    if len(units) <= 1:
        return []

    total_chars = max(1, sum(len(unit) for unit in units))
    total_duration = max(1, seg.end_ms - seg.start_ms)
    assigned: dict[int, list[str]] = {}
    consumed = 0
    for unit in units:
        unit_start = consumed
        consumed += len(unit)
        unit_mid_ms = seg.start_ms + round(((unit_start + consumed) / 2) / total_chars * total_duration)
        interval_index = _interval_index_for_timestamp(unit_mid_ms, intervals)
        assigned.setdefault(interval_index, []).append(unit)

    pieces: list[Segment] = []
    for index, (left, right, speaker) in enumerate(intervals):
        piece_text = _cleanup_segment_text("".join(assigned.get(index, [])))
        if not piece_text:
            continue
        pieces.append(
            Segment(
                start_ms=left,
                end_ms=right,
                text=piece_text,
                speaker=speaker,
                confidence=seg.confidence,
            )
        )
    return pieces


def _interval_index_for_timestamp(ts_ms: int, intervals: list[tuple[int, int, str]]) -> int:
    for index, (left, right, _) in enumerate(intervals):
        if left <= ts_ms < right:
            return index
    return min(
        range(len(intervals)),
        key=lambda index: min(abs(ts_ms - intervals[index][0]), abs(ts_ms - intervals[index][1])),
    )


def _best_overlap_speaker(start_ms: int, end_ms: int, diar_segments: list[Segment]) -> str | None:
    best_speaker = None
    best_overlap = -1
    for diar_seg in diar_segments:
        overlap_start = max(start_ms, diar_seg.start_ms)
        overlap_end = min(end_ms, diar_seg.end_ms)
        overlap = max(0, overlap_end - overlap_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = diar_seg.speaker
    return best_speaker


def _nearest_speaker(ts_ms: int, diar_segments: list[Segment]) -> str | None:
    """找到给定时间点最近的说话人段落。"""
    if not diar_segments:
        return None
    nearest = min(
        diar_segments,
        key=lambda s: min(abs(ts_ms - s.start_ms), abs(ts_ms - s.end_ms))
    )
    return nearest.speaker


def merge_short_segments(
    segments: list[Segment],
    min_duration_ms: int = 500,
    max_speaker_gap_ms: int = 300,
    max_merged_duration_ms: int = 15000,
) -> list[Segment]:
    """合并过短的段落，减少噪声。

    规则：
    - 短于 min_duration_ms 的段落合并到最近的段落
    - 相邻同说话人段落合并
    - 相邻不同说话人的短间隙（< max_speaker_gap_ms）合并
    """
    if len(segments) <= 1:
        return segments

    normalized = sorted(
        [
            segment.model_copy(
                update={
                    "text": _cleanup_segment_text(segment.text),
                }
            )
            for segment in segments
        ],
        key=lambda item: (item.start_ms, item.end_ms),
    )
    merged: list[Segment] = []
    current = normalized[0]

    for seg in normalized[1:]:
        seg_len = seg.end_ms - seg.start_ms
        gap = seg.start_ms - current.end_ms

        # 短段落合并到当前段
        if seg_len < min_duration_ms and gap < max_speaker_gap_ms and seg.speaker == current.speaker:
            current = current.model_copy(
                update={
                    "end_ms": max(current.end_ms, seg.end_ms),
                    "text": _join_text(current.text, seg.text),
                }
            )
            continue

        # 相邻同说话人合并，但限制最大可读时长，避免大段糊成一坨
        if (
            seg.speaker == current.speaker
            and gap <= max_speaker_gap_ms
            and (max(seg.end_ms, current.end_ms) - current.start_ms) <= max_merged_duration_ms
        ):
            current = current.model_copy(
                update={
                    "end_ms": max(current.end_ms, seg.end_ms),
                    "text": _join_text(current.text, seg.text),
                }
            )
        else:
            merged.append(current)
            current = seg

    merged.append(current)
    smoothed = _merge_tiny_alternating_segments(merged, min_duration_ms=min_duration_ms)
    split_segments = _split_long_segments(smoothed, max_duration_ms=max_merged_duration_ms)
    compacted = _merge_tiny_same_speaker_followups(split_segments)
    repaired = _repair_adjacent_same_speaker_boundaries(compacted)
    return [segment for segment in repaired if _cleanup_segment_text(segment.text)]


def _join_text(left: str, right: str) -> str:
    left = _cleanup_segment_text(left)
    right = _cleanup_segment_text(right)
    if not left:
        return right
    if not right:
        return left
    overlap = _find_text_overlap(left, right)
    right = right[overlap:] if overlap else right
    if not right:
        return left
    return _cleanup_segment_text(f"{left} {right}")


def _find_text_overlap(left: str, right: str, min_overlap: int = 2, max_window: int = 24) -> int:
    left = left.strip()
    right = right.strip()
    max_len = min(len(left), len(right), max_window)
    for size in range(max_len, min_overlap - 1, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def _merge_tiny_alternating_segments(segments: list[Segment], min_duration_ms: int) -> list[Segment]:
    if len(segments) <= 2:
        return segments

    items = [segment.model_copy() for segment in segments]
    tiny_text_len = 6
    index = 1
    while index < len(items) - 1:
        current = items[index]
        prev_seg = items[index - 1]
        next_seg = items[index + 1]
        duration = current.end_ms - current.start_ms
        if (
            duration <= max(min_duration_ms * 3, 2500)
            or len(_cleanup_segment_text(current.text)) <= tiny_text_len
            or _is_filler_segment(current.text)
        ):
            if prev_seg.speaker == next_seg.speaker:
                merged_text = _join_text(prev_seg.text, next_seg.text)
                items[index - 1] = prev_seg.model_copy(
                    update={
                        "end_ms": next_seg.end_ms,
                        "text": merged_text,
                    }
                )
                items.pop(index + 1)
                items.pop(index)
                index = max(1, index - 1)
                continue
        index += 1
    return items


def _split_long_segments(segments: list[Segment], max_duration_ms: int) -> list[Segment]:
    result: list[Segment] = []
    for segment in segments:
        duration = segment.end_ms - segment.start_ms
        text = _cleanup_segment_text(segment.text)
        if duration <= max_duration_ms or not text:
            result.append(segment)
            continue

        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;，,])", text) if item.strip()]
        if len(sentences) <= 1:
            result.append(segment)
            continue

        total_chars = max(1, sum(len(item) for item in sentences))
        cursor = segment.start_ms
        split_segments: list[Segment] = []
        for idx, sentence in enumerate(sentences):
            if idx == len(sentences) - 1:
                end_ms = segment.end_ms
            else:
                share = max(1, round(duration * len(sentence) / total_chars))
                end_ms = min(segment.end_ms, cursor + share)
            split_segments.append(
                segment.model_copy(
                    update={
                        "start_ms": cursor,
                        "end_ms": max(cursor + 1, end_ms),
                        "text": _cleanup_segment_text(sentence),
                    }
                )
            )
            cursor = split_segments[-1].end_ms
        if split_segments:
            split_segments[-1] = split_segments[-1].model_copy(update={"end_ms": segment.end_ms})
        result.extend(split_segments)
    return result


def _merge_tiny_same_speaker_followups(
    segments: list[Segment],
    max_gap_ms: int = 2000,
    max_tiny_duration_ms: int = 900,
    max_tiny_text_len: int = 4,
) -> list[Segment]:
    if len(segments) <= 1:
        return segments

    merged: list[Segment] = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        gap_ms = segment.start_ms - previous.end_ms
        segment_text = _cleanup_segment_text(segment.text)
        segment_duration_ms = segment.end_ms - segment.start_ms
        is_short_fragment = segment_duration_ms <= max_tiny_duration_ms
        is_short_unpunctuated_tail = (
            len(segment_text) <= max_tiny_text_len
            and not re.search(r"[。！？!?；;]$", segment_text)
        )
        if (
            previous.speaker == segment.speaker
            and 0 <= gap_ms <= max_gap_ms
            and (
                is_short_fragment
                or is_short_unpunctuated_tail
                or _is_filler_segment(segment_text)
            )
        ):
            merged[-1] = previous.model_copy(
                update={
                    "end_ms": max(previous.end_ms, segment.end_ms),
                    "text": _join_text(previous.text, segment.text),
                }
            )
            continue
        merged.append(segment)
    return merged


def _repair_adjacent_same_speaker_boundaries(segments: list[Segment]) -> list[Segment]:
    if len(segments) <= 1:
        return [
            segment.model_copy(update={"text": _trim_leading_punctuation(segment.text)})
            for segment in segments
        ]

    repaired = [segment.model_copy(update={"text": _trim_leading_punctuation(segment.text)}) for segment in segments]
    for index in range(1, len(repaired)):
        previous = repaired[index - 1]
        current = repaired[index]
        if previous.speaker != current.speaker:
            repaired[index] = current.model_copy(update={"text": _trim_leading_punctuation(current.text)})
            continue

        previous_text = _cleanup_segment_text(previous.text)
        current_text = _trim_leading_punctuation(current.text)
        if not previous_text or not current_text:
            repaired[index - 1] = previous.model_copy(update={"text": previous_text})
            repaired[index] = current.model_copy(update={"text": current_text})
            continue

        shifted_previous, shifted_current = _repair_cjk_boundary(previous_text, current_text)
        repaired[index - 1] = previous.model_copy(update={"text": shifted_previous})
        repaired[index] = current.model_copy(update={"text": shifted_current})

    return repaired


def _repair_cjk_boundary(previous_text: str, current_text: str) -> tuple[str, str]:
    prev = _cleanup_segment_text(previous_text)
    curr = _trim_leading_punctuation(current_text)
    if not prev or not curr:
        return prev, curr
    if re.search(r"[。！？!?；;]$", prev):
        return prev, curr

    if not re.search(r"[\u4e00-\u9fff]$", prev) or not re.match(r"^[\u4e00-\u9fff]", curr):
        return prev, curr

    prev_last = prev[-1]
    curr_head = re.match(r"^([\u4e00-\u9fff]{1,4})", curr)
    if curr.startswith(prev_last):
        prev = prev[:-1].rstrip(" ,，")
        return _cleanup_segment_text(prev), _cleanup_segment_text(curr)

    if not curr_head:
        return prev, curr

    head = curr_head.group(1)
    if _looks_like_split_cjk_word(prev, head):
        prev = prev[:-1].rstrip(" ,，")
        curr = f"{prev_last}{curr}"
    return _cleanup_segment_text(prev), _cleanup_segment_text(curr)


def _looks_like_split_cjk_word(previous_text: str, current_head: str) -> bool:
    if len(previous_text) < 3 or not current_head:
        return False

    if len(current_head) == 1:
        return True

    second_char_particles = {
        "的",
        "了",
        "地",
        "得",
        "时",
        "后",
        "是",
        "把",
        "被",
        "让",
        "就",
        "也",
        "都",
        "要",
        "能",
        "可",
        "在",
    }
    return current_head[1] in second_char_particles


def _trim_leading_punctuation(text: str | None) -> str:
    cleaned = _cleanup_segment_text(text)
    return re.sub(r"^[。！？；，,.!?;、]+", "", cleaned).strip()


def _cleanup_segment_text(text: str | None) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)
    cleaned = re.sub(r"([，。！？；,.!?;])\1+", r"\1", cleaned)
    cleaned = _dedupe_adjacent_phrase(cleaned)
    cleaned = _dedupe_stutter_tokens(cleaned)
    return cleaned.strip(" ,，")


def _dedupe_adjacent_phrase(text: str) -> str:
    cleaned = text
    for size in range(2, 13):
        pattern = re.compile(rf"(.{{{size}}})(?:\s*[，。！？；,.!?;]?\s*)\1+")
        while True:
            updated = pattern.sub(r"\1", cleaned)
            if updated == cleaned:
                break
            cleaned = updated
    return cleaned


def _dedupe_stutter_tokens(text: str) -> str:
    parts = [item for item in re.split(r"(\s+)", text) if item]
    result: list[str] = []
    previous_normalized = ""
    for part in parts:
        if part.isspace():
            if result and not result[-1].isspace():
                result.append(" ")
            continue
        normalized = re.sub(r"[，。！？；,.!?;]", "", part)
        if normalized and normalized == previous_normalized and len(normalized) <= 4:
            continue
        result.append(part)
        if normalized:
            previous_normalized = normalized
    return "".join(result)


def _is_filler_segment(text: str | None) -> bool:
    normalized = re.sub(r"[，。！？；,.!?;\s]", "", _cleanup_segment_text(text))
    if not normalized:
        return True
    fillers = {
        "啊",
        "嗯",
        "呃",
        "额",
        "唉",
        "欸",
        "哦",
        "哎",
        "然后",
        "那个",
        "就是",
    }
    return normalized in fillers


def _max_confidence(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
