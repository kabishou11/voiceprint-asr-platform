from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PUNCTUATION_PATTERN = re.compile(r"[，。！？；：、“”‘’,.!?;:~\-—_\(\)\[\]{}<>《》/\\|]")
_READABLE_SEGMENT_PATTERN = re.compile(
    r"^\d+\.\s+\[(?P<start>[\d:.]+)\s+-\s+(?P<end>[\d:.]+)\s+\|\s+[\d:.]+\]\s+(?P<speaker>\S+)\s*$"
)


@dataclass(frozen=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptArtifact:
    text: str
    language: str | None
    segments: list[TranscriptSegment]
    metadata: dict[str, Any]


def normalize_compare_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"file:\s*.*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*+result\*+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = _PUNCTUATION_PATTERN.sub("", cleaned)
    return cleaned.lower()


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (0 if left_char == right_char else 1)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    normalized_reference = normalize_compare_text(reference)
    normalized_hypothesis = normalize_compare_text(hypothesis)
    if not normalized_reference:
        return 0.0 if not normalized_hypothesis else 1.0
    return levenshtein_distance(normalized_reference, normalized_hypothesis) / len(normalized_reference)


def sequence_ratio(reference: str, hypothesis: str) -> float:
    return difflib.SequenceMatcher(
        a=normalize_compare_text(reference),
        b=normalize_compare_text(hypothesis),
    ).ratio()


def hotword_recall(reference_hotwords: list[str], hypothesis: str) -> dict[str, Any]:
    hotwords = [word.strip() for word in reference_hotwords if word.strip()]
    if not hotwords:
        return {
            "available": False,
            "total": 0,
            "matched": 0,
            "recall": None,
            "missing": [],
        }
    normalized_hypothesis = normalize_compare_text(hypothesis)
    missing = [
        word
        for word in hotwords
        if normalize_compare_text(word) not in normalized_hypothesis
    ]
    matched = len(hotwords) - len(missing)
    return {
        "available": True,
        "total": len(hotwords),
        "matched": matched,
        "recall": matched / len(hotwords),
        "missing": missing,
    }


def text_quality_metrics(
    *,
    reference_text: str | None,
    hypothesis_text: str,
    hotwords: list[str] | None = None,
) -> dict[str, Any]:
    if not reference_text:
        return {
            "available": False,
            "hypothesis_length": len(normalize_compare_text(hypothesis_text)),
            "hotword_recall": hotword_recall(hotwords or [], hypothesis_text),
        }

    normalized_reference = normalize_compare_text(reference_text)
    normalized_hypothesis = normalize_compare_text(hypothesis_text)
    return {
        "available": True,
        "cer": character_error_rate(reference_text, hypothesis_text),
        "sequence_ratio": sequence_ratio(reference_text, hypothesis_text),
        "reference_length": len(normalized_reference),
        "hypothesis_length": len(normalized_hypothesis),
        "length_delta": len(normalized_hypothesis) - len(normalized_reference),
        "hotword_recall": hotword_recall(hotwords or [], hypothesis_text),
    }


def speaker_diagnostics(
    segments: list[TranscriptSegment],
    *,
    short_fragment_ms: int = 1500,
    long_segment_ms: int = 15000,
) -> dict[str, Any]:
    if not segments:
        return {"available": False, "segment_count": 0}

    speaker_durations: dict[str, int] = {}
    short_count = 0
    long_count = 0
    turns = 0
    previous_speaker: str | None = None
    min_start = min(segment.start_ms for segment in segments)
    max_end = max(segment.end_ms for segment in segments)

    for segment in segments:
        duration = max(0, segment.end_ms - segment.start_ms)
        speaker = segment.speaker or "UNKNOWN"
        speaker_durations[speaker] = speaker_durations.get(speaker, 0) + duration
        if duration <= short_fragment_ms:
            short_count += 1
        if duration >= long_segment_ms:
            long_count += 1
        if previous_speaker is not None and speaker != previous_speaker:
            turns += 1
        previous_speaker = speaker

    timeline_duration_ms = max(1, max_end - min_start)
    speech_duration_ms = sum(speaker_durations.values())
    return {
        "available": True,
        "segment_count": len(segments),
        "speaker_count": len(speaker_durations),
        "timeline_duration_ms": timeline_duration_ms,
        "speech_duration_ms": speech_duration_ms,
        "speaker_durations": speaker_durations,
        "speaker_duration_share": {
            speaker: duration / max(1, speech_duration_ms)
            for speaker, duration in speaker_durations.items()
        },
        "short_fragment_count": short_count,
        "short_fragment_ratio": short_count / len(segments),
        "long_segment_count": long_count,
        "speaker_turn_count": turns,
        "speaker_turns_per_minute": turns / max(1.0, timeline_duration_ms / 60000.0),
        "average_segment_ms": speech_duration_ms / len(segments),
    }


def diarization_error_metrics(
    reference_segments: list[TranscriptSegment],
    hypothesis_segments: list[TranscriptSegment],
    *,
    frame_step_ms: int = 100,
) -> dict[str, Any]:
    """Compute lightweight DER/JER-style diagnostics from speaker annotations.

    The implementation samples the timeline at a fixed frame step and applies a
    greedy speaker-label mapping. It intentionally stays dependency-free so the
    evaluation script works on Windows without pyannote-metrics.
    """
    reference = _valid_speaker_segments(reference_segments)
    hypothesis = _valid_speaker_segments(hypothesis_segments)
    if not reference:
        return {"available": False, "reason": "missing_reference_speakers"}

    frame_step_ms = max(10, int(frame_step_ms))
    start_ms = min(
        [segment.start_ms for segment in reference]
        + [segment.start_ms for segment in hypothesis]
    )
    end_ms = max(
        [segment.end_ms for segment in reference]
        + [segment.end_ms for segment in hypothesis]
    )
    if end_ms <= start_ms:
        return {"available": False, "reason": "empty_timeline"}

    reference_labels = _frame_speaker_labels(reference, start_ms, end_ms, frame_step_ms)
    hypothesis_labels = _frame_speaker_labels(hypothesis, start_ms, end_ms, frame_step_ms)
    mapping = _greedy_speaker_mapping(reference_labels, hypothesis_labels)

    miss = 0
    false_alarm = 0
    confusion = 0
    reference_speech = 0
    for reference_label, hypothesis_label in zip(reference_labels, hypothesis_labels):
        if reference_label is not None:
            reference_speech += 1
        if reference_label is not None and hypothesis_label is None:
            miss += 1
            continue
        if reference_label is None and hypothesis_label is not None:
            false_alarm += 1
            continue
        if reference_label is None and hypothesis_label is None:
            continue
        mapped_hypothesis = mapping.get(str(hypothesis_label), hypothesis_label)
        if mapped_hypothesis != reference_label:
            confusion += 1

    denominator = max(1, reference_speech)
    return {
        "available": True,
        "frame_step_ms": frame_step_ms,
        "reference_speaker_count": len({segment.speaker for segment in reference}),
        "hypothesis_speaker_count": len({segment.speaker for segment in hypothesis}),
        "speaker_mapping": mapping,
        "der": (miss + false_alarm + confusion) / denominator,
        "miss_rate": miss / denominator,
        "false_alarm_rate": false_alarm / denominator,
        "confusion_rate": confusion / denominator,
        "jer": _jaccard_error_rate(reference_labels, hypothesis_labels, mapping),
        "miss_ms": miss * frame_step_ms,
        "false_alarm_ms": false_alarm * frame_step_ms,
        "confusion_ms": confusion * frame_step_ms,
        "reference_speech_ms": reference_speech * frame_step_ms,
    }


def voiceprint_diagnostics(
    metadata: dict[str, Any],
    *,
    low_confidence_threshold: float = 0.65,
) -> dict[str, Any]:
    matches = metadata.get("voiceprint_matches") or []
    if not isinstance(matches, list) or not matches:
        return {"available": False, "speaker_count": 0}

    top_scores: dict[str, float | None] = {}
    low_confidence: list[str] = []
    matched_count = 0
    error_count = 0
    for item in matches:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "UNKNOWN")
        candidates = item.get("candidates") or []
        top_score = None
        if candidates and isinstance(candidates[0], dict):
            top_score = float(candidates[0].get("score") or 0.0)
        top_scores[speaker] = top_score
        if item.get("matched"):
            matched_count += 1
        if item.get("error"):
            error_count += 1
        if top_score is None or top_score < low_confidence_threshold:
            low_confidence.append(speaker)

    speaker_count = len(top_scores)
    return {
        "available": True,
        "speaker_count": speaker_count,
        "matched_speaker_count": matched_count,
        "unmatched_speaker_count": max(0, speaker_count - matched_count),
        "error_count": error_count,
        "low_confidence_threshold": low_confidence_threshold,
        "low_confidence_count": len(low_confidence),
        "low_confidence_speakers": low_confidence,
        "top_candidate_scores": top_scores,
    }


def voiceprint_threshold_scan(
    metadata: dict[str, Any],
    ground_truth: dict[str, str] | None,
    *,
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    matches = metadata.get("voiceprint_matches") or []
    if not isinstance(matches, list) or not matches:
        return {"available": False, "reason": "missing_voiceprint_matches"}
    if not ground_truth:
        return {"available": False, "reason": "missing_voiceprint_ground_truth"}

    score_rows = _voiceprint_score_rows(matches, ground_truth)
    if not score_rows:
        return {"available": False, "reason": "missing_candidate_scores"}

    thresholds = thresholds or [round(index / 100, 2) for index in range(0, 101)]
    points = []
    best_eer: dict[str, Any] | None = None
    for threshold in sorted(set(float(item) for item in thresholds)):
        tp = fp = tn = fn = 0
        for row in score_rows:
            predicted = row["score"] >= threshold
            actual = bool(row["is_match"])
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
            elif not predicted and actual:
                fn += 1
            else:
                tn += 1

        tpr = tp / max(1, tp + fn)
        fpr = fp / max(1, fp + tn)
        fnr = fn / max(1, fn + tp)
        precision = tp / max(1, tp + fp)
        point = {
            "threshold": threshold,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "tpr": tpr,
            "fpr": fpr,
            "fnr": fnr,
            "precision": precision,
            "recall": tpr,
        }
        points.append(point)
        gap = abs(fpr - fnr)
        if best_eer is None or gap < best_eer["gap"]:
            best_eer = {
                "threshold": threshold,
                "eer": (fpr + fnr) / 2,
                "gap": gap,
                "fpr": fpr,
                "fnr": fnr,
            }

    positive_count = sum(1 for row in score_rows if row["is_match"])
    return {
        "available": True,
        "label_count": len(ground_truth),
        "sample_count": len(score_rows),
        "positive_count": positive_count,
        "negative_count": len(score_rows) - positive_count,
        "approx_eer": best_eer,
        "roc_points": points,
    }


def minutes_coverage_diagnostics(minutes_payload: dict[str, Any] | None, transcript_text: str) -> dict[str, Any]:
    if not minutes_payload:
        return {"available": False}

    transcript_normalized = normalize_compare_text(transcript_text)

    def score_items(key: str) -> dict[str, Any]:
        raw_items = minutes_payload.get(key) or []
        items = [str(item).strip() for item in raw_items if str(item).strip()]
        if not items:
            return {"total": 0, "covered": 0, "coverage": None, "missing": []}
        missing = [
            item
            for item in items
            if not _has_text_evidence(item, transcript_normalized)
        ]
        covered = len(items) - len(missing)
        return {
            "total": len(items),
            "covered": covered,
            "coverage": covered / len(items),
            "missing": missing,
        }

    return {
        "available": True,
        "decisions": score_items("decisions"),
        "action_items": score_items("action_items"),
        "risks": score_items("risks"),
    }


def build_core_pipeline_report(
    *,
    transcript: TranscriptArtifact,
    reference_text: str | None = None,
    reference_speaker_segments: list[TranscriptSegment] | None = None,
    hotwords: list[str] | None = None,
    minutes_payload: dict[str, Any] | None = None,
    low_confidence_threshold: float = 0.65,
    voiceprint_ground_truth: dict[str, str] | None = None,
    voiceprint_thresholds: list[float] | None = None,
    speaker_frame_step_ms: int = 100,
) -> dict[str, Any]:
    transcript_text = transcript.text or "\n".join(segment.text for segment in transcript.segments)
    return {
        "summary": {
            "language": transcript.language,
            "text_length": len(transcript_text),
            "segment_count": len(transcript.segments),
        },
        "asr": text_quality_metrics(
            reference_text=reference_text,
            hypothesis_text=transcript_text,
            hotwords=hotwords or [],
        ),
        "speakers": speaker_diagnostics(transcript.segments),
        "speaker_reference": diarization_error_metrics(
            reference_speaker_segments or [],
            transcript.segments,
            frame_step_ms=speaker_frame_step_ms,
        ) if reference_speaker_segments is not None else {"available": False},
        "voiceprint": voiceprint_diagnostics(
            transcript.metadata,
            low_confidence_threshold=low_confidence_threshold,
        ),
        "voiceprint_threshold_scan": voiceprint_threshold_scan(
            transcript.metadata,
            voiceprint_ground_truth,
            thresholds=voiceprint_thresholds,
        ),
        "minutes": minutes_coverage_diagnostics(minutes_payload, transcript_text),
    }


def load_transcript_artifact(path: str | Path) -> TranscriptArtifact:
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return _parse_readable_transcript(payload)
    if isinstance(data, dict):
        return _parse_json_transcript(data)
    raise ValueError(f"不支持的转写产物格式: {source}")


def load_minutes_payload(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        return data
    raise ValueError("会议纪要 JSON 必须是对象或序列化后的对象字符串")


def load_speaker_reference(path: str | Path | None) -> list[TranscriptSegment] | None:
    if not path:
        return None
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".rttm":
        return _parse_rttm_speakers(payload)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return _parse_readable_transcript(payload).segments
    if isinstance(data, dict):
        return _parse_json_transcript(data).segments
    raise ValueError("speaker 标注文件必须是 RTTM、TranscriptResult JSON 或 readable txt")


def load_voiceprint_labels(path: str | Path | None) -> dict[str, str] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("speakers"), dict):
        data = data["speakers"]
    if not isinstance(data, dict):
        raise ValueError("声纹标签文件必须是 {speaker: profile_id} 或 {speakers: {...}} JSON")

    labels: dict[str, str] = {}
    for speaker, value in data.items():
        if isinstance(value, dict):
            label = value.get("profile_id") or value.get("display_name") or value.get("label")
        else:
            label = value
        if str(speaker).strip() and str(label or "").strip():
            labels[str(speaker).strip()] = str(label).strip()
    return labels


def load_hotwords(path: str | Path | None) -> list[str]:
    if not path:
        return []
    payload = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(payload)
        words = data.get("hotwords") if isinstance(data, dict) else data
        return [str(item).strip() for item in (words or []) if str(item).strip()]
    return [line.strip() for line in payload.splitlines() if line.strip()]


def render_markdown_report(report: dict[str, Any]) -> str:
    asr = report.get("asr") or {}
    speakers = report.get("speakers") or {}
    speaker_reference = report.get("speaker_reference") or {}
    voiceprint = report.get("voiceprint") or {}
    voiceprint_scan = report.get("voiceprint_threshold_scan") or {}
    minutes = report.get("minutes") or {}

    lines = [
        "# 核心流水线评测报告",
        "",
        "## ASR",
        f"- CER: {_format_percent(asr.get('cer'))}",
        f"- 文本相似度: {_format_percent(asr.get('sequence_ratio'))}",
        f"- 参考长度: {asr.get('reference_length', 'N/A')}",
        f"- 识别长度: {asr.get('hypothesis_length', 'N/A')}",
        f"- 热词召回: {_format_percent((asr.get('hotword_recall') or {}).get('recall'))}",
        "",
        "## Speaker 诊断",
        f"- Speaker 数: {speakers.get('speaker_count', 'N/A')}",
        f"- 分段数: {speakers.get('segment_count', 'N/A')}",
        f"- 短碎片率: {_format_percent(speakers.get('short_fragment_ratio'))}",
        f"- 每分钟换人次数: {_format_number(speakers.get('speaker_turns_per_minute'))}",
        f"- 过长段数量: {speakers.get('long_segment_count', 'N/A')}",
        "",
        "## Speaker 标注对比",
        f"- 可用: {bool(speaker_reference.get('available'))}",
        f"- DER: {_format_percent(speaker_reference.get('der'))}",
        f"- JER: {_format_percent(speaker_reference.get('jer'))}",
        f"- Miss: {_format_percent(speaker_reference.get('miss_rate'))}",
        f"- False Alarm: {_format_percent(speaker_reference.get('false_alarm_rate'))}",
        f"- Confusion: {_format_percent(speaker_reference.get('confusion_rate'))}",
        "",
        "## 声纹识别",
        f"- 可用: {bool(voiceprint.get('available'))}",
        f"- 成功匹配 speaker: {voiceprint.get('matched_speaker_count', 'N/A')}",
        f"- 低置信 speaker: {voiceprint.get('low_confidence_count', 'N/A')}",
        "",
        "## 声纹阈值扫描",
        f"- 可用: {bool(voiceprint_scan.get('available'))}",
        f"- 样本数: {voiceprint_scan.get('sample_count', 'N/A')}",
        f"- 近似 EER: {_format_percent((voiceprint_scan.get('approx_eer') or {}).get('eer'))}",
        f"- EER 阈值: {_format_number((voiceprint_scan.get('approx_eer') or {}).get('threshold'))}",
        "",
        "## 会议纪要覆盖",
        f"- 可用: {bool(minutes.get('available'))}",
        f"- 决策覆盖: {_format_percent((minutes.get('decisions') or {}).get('coverage'))}",
        f"- 行动项覆盖: {_format_percent((minutes.get('action_items') or {}).get('coverage'))}",
        f"- 风险覆盖: {_format_percent((minutes.get('risks') or {}).get('coverage'))}",
    ]
    return "\n".join(lines) + "\n"


def _parse_json_transcript(data: dict[str, Any]) -> TranscriptArtifact:
    if isinstance(data.get("result"), dict):
        data = data["result"]
    elif isinstance(data.get("transcript"), dict):
        data = data["transcript"]

    segments = [
        TranscriptSegment(
            start_ms=int(item.get("start_ms") or 0),
            end_ms=int(item.get("end_ms") or 0),
            text=str(item.get("text") or ""),
            speaker=str(item["speaker"]) if item.get("speaker") is not None else None,
            confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
        )
        for item in data.get("segments") or []
        if isinstance(item, dict)
    ]
    return TranscriptArtifact(
        text=str(data.get("text") or "\n".join(segment.text for segment in segments)),
        language=str(data["language"]) if data.get("language") is not None else None,
        segments=segments,
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    )


def _parse_readable_transcript(payload: str) -> TranscriptArtifact:
    language_match = re.search(r"^语言:\s*(?P<language>.+)$", payload, flags=re.MULTILINE)
    language = language_match.group("language").strip() if language_match else None
    segments: list[TranscriptSegment] = []
    current: dict[str, Any] | None = None
    text_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current, text_lines
        if current is None:
            return
        segments.append(
            TranscriptSegment(
                start_ms=current["start_ms"],
                end_ms=current["end_ms"],
                text="\n".join(text_lines).strip(),
                speaker=current["speaker"],
            )
        )
        current = None
        text_lines = []

    for line in payload.splitlines():
        match = _READABLE_SEGMENT_PATTERN.match(line.strip())
        if match:
            flush_current()
            current = {
                "start_ms": _parse_time_ms(match.group("start")),
                "end_ms": _parse_time_ms(match.group("end")),
                "speaker": match.group("speaker"),
            }
            continue
        if current is not None:
            text_lines.append(line)
    flush_current()

    text = "\n".join(segment.text for segment in segments if segment.text)
    return TranscriptArtifact(text=text, language=language, segments=segments, metadata={})


def _parse_rttm_speakers(payload: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for line in payload.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 8 or parts[0].upper() != "SPEAKER":
            continue
        start_ms = round(float(parts[3]) * 1000)
        duration_ms = round(float(parts[4]) * 1000)
        speaker = parts[7]
        segments.append(
            TranscriptSegment(
                start_ms=start_ms,
                end_ms=start_ms + duration_ms,
                text="",
                speaker=speaker,
            )
        )
    return segments


def _parse_time_ms(value: str) -> int:
    hours, minutes, seconds = value.split(":")
    return int(
        (int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000
    )


def _has_text_evidence(item: str, transcript_normalized: str) -> bool:
    normalized_item = normalize_compare_text(item)
    if not normalized_item:
        return False
    if normalized_item in transcript_normalized:
        return True
    tokens = [
        token
        for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", normalized_item)
        if len(token) >= 2
    ]
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in transcript_normalized)
    return matched / len(tokens) >= 0.6


def _valid_speaker_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    return [
        segment
        for segment in segments
        if segment.speaker and segment.end_ms > segment.start_ms
    ]


def _frame_speaker_labels(
    segments: list[TranscriptSegment],
    start_ms: int,
    end_ms: int,
    frame_step_ms: int,
) -> list[str | None]:
    labels: list[str | None] = []
    ordered = sorted(segments, key=lambda item: (item.start_ms, item.end_ms, item.speaker or ""))
    for frame_start in range(start_ms, end_ms, frame_step_ms):
        midpoint = frame_start + frame_step_ms / 2
        active = [
            segment
            for segment in ordered
            if segment.start_ms <= midpoint < segment.end_ms
        ]
        if not active:
            labels.append(None)
            continue
        # If annotations overlap, choose the longest active segment for this
        # lightweight single-label metric.
        winner = max(active, key=lambda item: item.end_ms - item.start_ms)
        labels.append(winner.speaker)
    return labels


def _greedy_speaker_mapping(
    reference_labels: list[str | None],
    hypothesis_labels: list[str | None],
) -> dict[str, str]:
    overlaps: dict[tuple[str, str], int] = {}
    for reference_label, hypothesis_label in zip(reference_labels, hypothesis_labels):
        if reference_label is None or hypothesis_label is None:
            continue
        key = (str(hypothesis_label), str(reference_label))
        overlaps[key] = overlaps.get(key, 0) + 1

    mapping: dict[str, str] = {}
    used_references: set[str] = set()
    for (hypothesis_label, reference_label), _ in sorted(
        overlaps.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        if hypothesis_label in mapping or reference_label in used_references:
            continue
        mapping[hypothesis_label] = reference_label
        used_references.add(reference_label)
    return mapping


def _jaccard_error_rate(
    reference_labels: list[str | None],
    hypothesis_labels: list[str | None],
    mapping: dict[str, str],
) -> float | None:
    reference_speakers = sorted({label for label in reference_labels if label is not None})
    if not reference_speakers:
        return None
    errors: list[float] = []
    for speaker in reference_speakers:
        intersection = 0
        union = 0
        for reference_label, hypothesis_label in zip(reference_labels, hypothesis_labels):
            mapped_hypothesis = mapping.get(str(hypothesis_label), hypothesis_label) if hypothesis_label else None
            reference_active = reference_label == speaker
            hypothesis_active = mapped_hypothesis == speaker
            if reference_active or hypothesis_active:
                union += 1
            if reference_active and hypothesis_active:
                intersection += 1
        errors.append(1.0 - (intersection / max(1, union)))
    return sum(errors) / len(errors)


def _voiceprint_score_rows(
    matches: list[Any],
    ground_truth: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        expected = ground_truth.get(speaker)
        if not expected:
            continue
        candidates = item.get("candidates") or []
        found_positive = False
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            profile_id = str(candidate.get("profile_id") or "")
            display_name = str(candidate.get("display_name") or "")
            score = float(candidate.get("score") or 0.0)
            is_match = expected in {profile_id, display_name}
            found_positive = found_positive or is_match
            rows.append(
                {
                    "speaker": speaker,
                    "profile_id": profile_id,
                    "display_name": display_name,
                    "score": score,
                    "is_match": is_match,
                }
            )
        if not found_positive:
            rows.append(
                {
                    "speaker": speaker,
                    "profile_id": expected,
                    "display_name": expected,
                    "score": 0.0,
                    "is_match": True,
                }
            )
    return rows


def _format_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}"
