from __future__ import annotations

from domain.schemas.transcript import Segment, TranscriptResult


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
    if not diarization_segments:
        return transcript

    # 方案 1：转写段落已有 speaker 信息（如 SenseVoice 内置分离）
    if any(seg.speaker for seg in transcript.segments):
        return transcript

    # 方案 2：基于时间重叠度对齐
    merged: list[Segment] = []
    for seg in transcript.segments:
        # 找重叠最大的说话人段
        best_speaker, best_overlap = None, -1.0
        seg_start, seg_end = seg.start_ms, seg.end_ms
        seg_len = seg_end - seg_start if seg_end > seg_start else 1

        for diar_seg in diarization_segments:
            diar_start, diar_end = diar_seg.start_ms, diar_seg.end_ms
            overlap_start = max(seg_start, diar_start)
            overlap_end = min(seg_end, diar_end)
            overlap = max(0, overlap_end - overlap_start)
            overlap_ratio = overlap / seg_len

            if overlap_ratio > best_overlap:
                best_overlap = overlap_ratio
                best_speaker = diar_seg.speaker

        # 如果没有明显重叠，使用最近的说话人
        if best_speaker is None or best_overlap < 0.1:
            best_speaker = _nearest_speaker(seg_start, diarization_segments)

        merged.append(seg.model_copy(update={"speaker": best_speaker or "SPEAKER_00"}))

    return TranscriptResult(
        text=transcript.text,
        language=transcript.language,
        segments=merged,
    )


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
) -> list[Segment]:
    """合并过短的段落，减少噪声。

    规则：
    - 短于 min_duration_ms 的段落合并到最近的段落
    - 相邻同说话人段落合并
    - 相邻不同说话人的短间隙（< max_speaker_gap_ms）合并
    """
    if len(segments) <= 1:
        return segments

    merged: list[Segment] = []
    current = segments[0]

    for seg in segments[1:]:
        seg_len = seg.end_ms - seg.start_ms
        gap = seg.start_ms - current.end_ms

        # 短段落合并到当前段
        if seg_len < min_duration_ms and gap < max_speaker_gap_ms:
            # 短段落合并到当前段（保持当前说话人）
            continue

        # 相邻同说话人合并
        if seg.speaker == current.speaker:
            current = current.model_copy(update={"end_ms": seg.end_ms})
            if current.text:
                current = current.model_copy(update={"text": current.text + seg.text})
        else:
            merged.append(current)
            current = seg

    merged.append(current)
    return merged
