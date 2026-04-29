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
    return levenshtein_distance(normalized_reference, normalized_hypothesis) / len(
        normalized_reference
    )


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
    for reference_label, hypothesis_label in zip(
        reference_labels,
        hypothesis_labels,
        strict=True,
    ):
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
            predicted = (
                False
                if row.get("missing_positive")
                else float(row["score"]) >= threshold
            )
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
    missing_positive_count = sum(1 for row in score_rows if row.get("missing_positive"))
    return {
        "available": True,
        "label_count": len(ground_truth),
        "sample_count": len(score_rows),
        "positive_count": positive_count,
        "negative_count": len(score_rows) - positive_count,
        "missing_positive_count": missing_positive_count,
        "approx_eer": best_eer,
        "roc_points": points,
    }


def voiceprint_identification_metrics(
    metadata: dict[str, Any],
    ground_truth: dict[str, str] | None,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    matches = metadata.get("voiceprint_matches") or []
    if not isinstance(matches, list) or not matches:
        return {"available": False, "reason": "missing_voiceprint_matches"}
    if not ground_truth:
        return {"available": False, "reason": "missing_voiceprint_ground_truth"}

    match_by_speaker = {
        str(item.get("speaker") or "").strip(): item
        for item in matches
        if isinstance(item, dict) and str(item.get("speaker") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    missing_result_speakers: list[str] = []
    missing_positive_speakers: list[str] = []
    wrong_top1_speakers: list[str] = []
    top1_hits = 0
    topk_hits = 0
    top_k = max(1, int(top_k))

    for speaker, expected in ground_truth.items():
        item = match_by_speaker.get(speaker)
        if not item:
            missing_result_speakers.append(speaker)
            missing_positive_speakers.append(speaker)
            rows.append(
                {
                    "speaker": speaker,
                    "expected": expected,
                    "top1_hit": False,
                    "topk_hit": False,
                    "missing_result": True,
                    "missing_positive": True,
                }
            )
            continue

        candidates = [
            candidate
            for candidate in (item.get("candidates") or [])
            if isinstance(candidate, dict)
        ]
        top_candidates = candidates[:top_k]
        top1 = top_candidates[0] if top_candidates else None
        top1_hit = bool(top1 and _voiceprint_candidate_matches(top1, expected))
        topk_hit = any(
            _voiceprint_candidate_matches(candidate, expected)
            for candidate in top_candidates
        )
        missing_positive = not any(
            _voiceprint_candidate_matches(candidate, expected)
            for candidate in candidates
        )

        if top1_hit:
            top1_hits += 1
        else:
            wrong_top1_speakers.append(speaker)
        if topk_hit:
            topk_hits += 1
        if missing_positive:
            missing_positive_speakers.append(speaker)

        rows.append(
            {
                "speaker": speaker,
                "expected": expected,
                "top1_profile_id": str(top1.get("profile_id") or "") if top1 else None,
                "top1_display_name": str(top1.get("display_name") or "") if top1 else None,
                "top1_score": float(top1.get("score") or 0.0) if top1 else None,
                "top1_hit": top1_hit,
                "topk_hit": topk_hit,
                "candidate_count": len(candidates),
                "missing_result": False,
                "missing_positive": missing_positive,
            }
        )

    evaluated_count = len(ground_truth)
    return {
        "available": True,
        "top_k": top_k,
        "label_count": len(ground_truth),
        "evaluated_speaker_count": evaluated_count,
        "top1_hit_count": top1_hits,
        "topk_hit_count": topk_hits,
        "top1_accuracy": top1_hits / max(1, evaluated_count),
        "topk_accuracy": topk_hits / max(1, evaluated_count),
        "missing_result_count": len(missing_result_speakers),
        "missing_result_speakers": missing_result_speakers,
        "missing_positive_count": len(missing_positive_speakers),
        "missing_positive_speakers": missing_positive_speakers,
        "wrong_top1_speakers": wrong_top1_speakers,
        "rows": rows,
    }


def minutes_coverage_diagnostics(
    minutes_payload: dict[str, Any] | None,
    transcript_text: str,
) -> dict[str, Any]:
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
        "voiceprint_identification": voiceprint_identification_metrics(
            transcript.metadata,
            voiceprint_ground_truth,
        ),
        "minutes": minutes_coverage_diagnostics(minutes_payload, transcript_text),
    }


def load_dataset_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("评测样本集 manifest 必须是 JSON 对象")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("评测样本集 manifest 必须包含非空 samples 数组")

    base_dir = manifest_path.parent
    resolved_samples: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict):
            raise ValueError(f"samples[{index}] 必须是对象")
        name = str(sample.get("name") or "").strip()
        transcript = str(sample.get("transcript") or "").strip()
        if not name:
            raise ValueError(f"samples[{index}] 缺少 name")
        if not transcript:
            raise ValueError(f"samples[{index}] 缺少 transcript")

        resolved = dict(sample)
        resolved["name"] = name
        for key in (
            "transcript",
            "reference_text",
            "reference_metadata",
            "reference_speakers",
            "hotwords_file",
            "minutes_json",
            "voiceprint_labels",
        ):
            value = sample.get(key)
            resolved[key] = str(_resolve_manifest_path(base_dir, value)) if value else None
        resolved_samples.append(resolved)

    manifest = dict(data)
    manifest["samples"] = resolved_samples
    return manifest


def build_core_pipeline_dataset_report(
    manifest: dict[str, Any],
    *,
    low_confidence_threshold: float = 0.65,
    speaker_frame_step_ms: int = 100,
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for sample in manifest.get("samples") or []:
        report = _build_manifest_sample_report(
            sample,
            low_confidence_threshold=low_confidence_threshold,
            speaker_frame_step_ms=speaker_frame_step_ms,
        )
        samples.append(report)

    return {
        "suite": {
            "name": manifest.get("suite_name") or manifest.get("name") or "core_pipeline_dataset",
            "version": manifest.get("version"),
            "description": manifest.get("description"),
            "sample_count": len(samples),
        },
        "aggregate": aggregate_core_pipeline_reports(samples),
        "samples": samples,
    }


def aggregate_core_pipeline_reports(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(samples),
        "asr": {
            "available_count": _available_count(samples, "asr"),
            "mean_cer": _mean_metric(samples, "asr", "cer"),
            "mean_sequence_ratio": _mean_metric(samples, "asr", "sequence_ratio"),
            "mean_hotword_recall": _mean_nested_metric(
                samples,
                "asr",
                "hotword_recall",
                "recall",
            ),
        },
        "speakers": {
            "available_count": _available_count(samples, "speakers"),
            "mean_speaker_count": _mean_metric(samples, "speakers", "speaker_count"),
            "mean_short_fragment_ratio": _mean_metric(
                samples,
                "speakers",
                "short_fragment_ratio",
            ),
            "mean_turns_per_minute": _mean_metric(
                samples,
                "speakers",
                "speaker_turns_per_minute",
            ),
        },
        "speaker_reference": {
            "available_count": _available_count(samples, "speaker_reference"),
            "mean_der": _mean_metric(samples, "speaker_reference", "der"),
            "mean_jer": _mean_metric(samples, "speaker_reference", "jer"),
        },
        "voiceprint": {
            "available_count": _available_count(samples, "voiceprint"),
            "mean_matched_speaker_count": _mean_metric(
                samples,
                "voiceprint",
                "matched_speaker_count",
            ),
            "mean_low_confidence_count": _mean_metric(
                samples,
                "voiceprint",
                "low_confidence_count",
            ),
        },
        "voiceprint_threshold_scan": {
            "available_count": _available_count(samples, "voiceprint_threshold_scan"),
            "mean_approx_eer": _mean_nested_metric(
                samples,
                "voiceprint_threshold_scan",
                "approx_eer",
                "eer",
            ),
        },
        "voiceprint_identification": {
            "available_count": _available_count(samples, "voiceprint_identification"),
            "mean_top1_accuracy": _mean_metric(
                samples,
                "voiceprint_identification",
                "top1_accuracy",
            ),
            "mean_topk_accuracy": _mean_metric(
                samples,
                "voiceprint_identification",
                "topk_accuracy",
            ),
            "mean_missing_positive_count": _mean_metric(
                samples,
                "voiceprint_identification",
                "missing_positive_count",
            ),
        },
        "minutes": {
            "available_count": _available_count(samples, "minutes"),
            "mean_decision_coverage": _mean_nested_metric(
                samples,
                "minutes",
                "decisions",
                "coverage",
            ),
            "mean_action_item_coverage": _mean_nested_metric(
                samples,
                "minutes",
                "action_items",
                "coverage",
            ),
            "mean_risk_coverage": _mean_nested_metric(
                samples,
                "minutes",
                "risks",
                "coverage",
            ),
        },
    }


def render_dataset_markdown_report(report: dict[str, Any]) -> str:
    suite = report.get("suite") or {}
    aggregate = report.get("aggregate") or {}
    samples = report.get("samples") or []
    asr = aggregate.get("asr") or {}
    speakers = aggregate.get("speakers") or {}
    speaker_reference = aggregate.get("speaker_reference") or {}
    voiceprint_scan = aggregate.get("voiceprint_threshold_scan") or {}
    voiceprint_identification = aggregate.get("voiceprint_identification") or {}
    minutes = aggregate.get("minutes") or {}

    lines = [
        "# 核心流水线样本集基线报告",
        "",
        f"- 样本集: {suite.get('name', 'N/A')}",
        f"- 版本: {suite.get('version') or 'N/A'}",
        f"- 样本数: {suite.get('sample_count', 0)}",
        "",
        "## 聚合指标",
        f"- 平均 CER: {_format_percent(asr.get('mean_cer'))}",
        f"- 平均文本相似度: {_format_percent(asr.get('mean_sequence_ratio'))}",
        f"- 平均热词召回: {_format_percent(asr.get('mean_hotword_recall'))}",
        f"- 平均 Speaker 数: {_format_number(speakers.get('mean_speaker_count'))}",
        f"- 平均短碎片率: {_format_percent(speakers.get('mean_short_fragment_ratio'))}",
        f"- 平均 DER: {_format_percent(speaker_reference.get('mean_der'))}",
        f"- 平均 JER: {_format_percent(speaker_reference.get('mean_jer'))}",
        f"- 平均近似 EER: {_format_percent(voiceprint_scan.get('mean_approx_eer'))}",
        f"- 平均声纹 Top1: "
        f"{_format_percent(voiceprint_identification.get('mean_top1_accuracy'))}",
        f"- 平均声纹 TopK: "
        f"{_format_percent(voiceprint_identification.get('mean_topk_accuracy'))}",
        f"- 平均决策覆盖: {_format_percent(minutes.get('mean_decision_coverage'))}",
        f"- 平均行动项覆盖: {_format_percent(minutes.get('mean_action_item_coverage'))}",
        f"- 平均风险覆盖: {_format_percent(minutes.get('mean_risk_coverage'))}",
        "",
        "## 样本明细",
        "| 样本 | CER | DER | JER | EER | Top1 | TopK | 决策覆盖 | 行动项覆盖 | 风险覆盖 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sample in samples:
        sample_asr = sample.get("asr") or {}
        sample_speaker_reference = sample.get("speaker_reference") or {}
        sample_voiceprint_scan = sample.get("voiceprint_threshold_scan") or {}
        sample_voiceprint_identification = sample.get("voiceprint_identification") or {}
        sample_minutes = sample.get("minutes") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str((sample.get("sample") or {}).get("name") or "N/A"),
                    _format_percent(sample_asr.get("cer")),
                    _format_percent(sample_speaker_reference.get("der")),
                    _format_percent(sample_speaker_reference.get("jer")),
                    _format_percent((sample_voiceprint_scan.get("approx_eer") or {}).get("eer")),
                    _format_percent(sample_voiceprint_identification.get("top1_accuracy")),
                    _format_percent(sample_voiceprint_identification.get("topk_accuracy")),
                    _format_percent((sample_minutes.get("decisions") or {}).get("coverage")),
                    _format_percent((sample_minutes.get("action_items") or {}).get("coverage")),
                    _format_percent((sample_minutes.get("risks") or {}).get("coverage")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def build_baseline_comparison_report(reports: list[dict[str, Any]]) -> dict[str, Any]:
    baselines = [_baseline_summary(report) for report in reports]
    reference = baselines[0] if baselines else None
    for baseline in baselines:
        baseline["delta_from_first"] = _baseline_delta(reference, baseline) if reference else {}
    return {
        "comparison": {
            "baseline_count": len(baselines),
            "reference": reference["name"] if reference else None,
        },
        "baselines": baselines,
    }


def load_baseline_report(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("aggregate"), dict):
        raise ValueError(f"不是有效的核心流水线 baseline JSON: {path}")
    return data


def render_baseline_comparison_markdown(report: dict[str, Any]) -> str:
    baselines = report.get("baselines") or []
    lines = [
        "# 核心流水线基线对比报告",
        "",
        f"- 基线数: {(report.get('comparison') or {}).get('baseline_count', 0)}",
        f"- 参考基线: {(report.get('comparison') or {}).get('reference') or 'N/A'}",
        "",
        "## 指标对比",
        "| 基线 | 样本数 | CER | DER | JER | EER | Top1 | TopK | "
        "决策覆盖 | 行动项覆盖 | 风险覆盖 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for baseline in baselines:
        metrics = baseline.get("metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(baseline.get("name") or "N/A"),
                    str(baseline.get("sample_count", 0)),
                    _format_percent(metrics.get("mean_cer")),
                    _format_percent(metrics.get("mean_der")),
                    _format_percent(metrics.get("mean_jer")),
                    _format_percent(metrics.get("mean_approx_eer")),
                    _format_percent(metrics.get("mean_voiceprint_top1_accuracy")),
                    _format_percent(metrics.get("mean_voiceprint_topk_accuracy")),
                    _format_percent(metrics.get("mean_decision_coverage")),
                    _format_percent(metrics.get("mean_action_item_coverage")),
                    _format_percent(metrics.get("mean_risk_coverage")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 相对首个基线变化",
            "| 基线 | CER | DER | JER | EER | Top1 | TopK | 决策覆盖 | 行动项覆盖 | 风险覆盖 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for baseline in baselines:
        delta = baseline.get("delta_from_first") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(baseline.get("name") or "N/A"),
                    _format_signed_percent(delta.get("mean_cer")),
                    _format_signed_percent(delta.get("mean_der")),
                    _format_signed_percent(delta.get("mean_jer")),
                    _format_signed_percent(delta.get("mean_approx_eer")),
                    _format_signed_percent(delta.get("mean_voiceprint_top1_accuracy")),
                    _format_signed_percent(delta.get("mean_voiceprint_topk_accuracy")),
                    _format_signed_percent(delta.get("mean_decision_coverage")),
                    _format_signed_percent(delta.get("mean_action_item_coverage")),
                    _format_signed_percent(delta.get("mean_risk_coverage")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


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
    voiceprint_identification = report.get("voiceprint_identification") or {}
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
        f"- Top1 命中率: {_format_percent(voiceprint_identification.get('top1_accuracy'))}",
        f"- TopK 命中率: {_format_percent(voiceprint_identification.get('topk_accuracy'))}",
        f"- 缺失正确候选: {voiceprint_identification.get('missing_positive_count', 'N/A')}",
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


def _build_manifest_sample_report(
    sample: dict[str, Any],
    *,
    low_confidence_threshold: float,
    speaker_frame_step_ms: int,
) -> dict[str, Any]:
    transcript_path = Path(str(sample["transcript"]))
    transcript = load_transcript_artifact(transcript_path)
    reference = _load_manifest_reference_text(sample)
    report = build_core_pipeline_report(
        transcript=transcript,
        reference_text=reference["text"] if reference["use_for_metrics"] else None,
        reference_speaker_segments=load_speaker_reference(sample.get("reference_speakers")),
        hotwords=load_hotwords(sample.get("hotwords_file")),
        minutes_payload=load_minutes_payload(sample.get("minutes_json")),
        low_confidence_threshold=low_confidence_threshold,
        voiceprint_ground_truth=load_voiceprint_labels(sample.get("voiceprint_labels")),
        speaker_frame_step_ms=speaker_frame_step_ms,
    )
    report["sample"] = {
        "name": sample["name"],
        "tags": sample.get("tags") or [],
        "notes": sample.get("notes"),
    }
    report["reference_text"] = {
        "path": sample.get("reference_text"),
        "metadata_path": reference.get("metadata_path"),
        "quality": reference["quality"],
        "slice_mode": (reference.get("metadata") or {}).get("reference_slice_mode"),
        "use_for_metrics": reference["use_for_metrics"],
        "warning": reference.get("warning"),
    }
    if reference["text"] and not reference["use_for_metrics"]:
        report["asr_diagnostic"] = text_quality_metrics(
            reference_text=reference["text"],
            hypothesis_text=transcript.text,
            hotwords=load_hotwords(sample.get("hotwords_file")),
        )
    report["inputs"] = {
        "transcript": str(transcript_path),
        "reference_text": sample.get("reference_text"),
        "reference_metadata": sample.get("reference_metadata"),
        "reference_speakers": sample.get("reference_speakers"),
        "hotwords_file": sample.get("hotwords_file"),
        "minutes_json": sample.get("minutes_json"),
        "voiceprint_labels": sample.get("voiceprint_labels"),
    }
    return report


def _load_manifest_reference_text(sample: dict[str, Any]) -> dict[str, Any]:
    reference_path = sample.get("reference_text")
    if not reference_path:
        return {"text": None, "quality": "missing", "use_for_metrics": False}

    path = Path(str(reference_path))
    text = path.read_text(encoding="utf-8")
    metadata_path = _reference_metadata_path(sample, path)
    metadata = _load_reference_metadata(metadata_path)
    explicit_quality = str(sample.get("reference_quality") or "").strip().lower()
    quality = explicit_quality or _infer_reference_quality(metadata)
    use_for_metrics = quality in {"confirmed", "gold", "manual", "aligned"}
    warning = None
    if not use_for_metrics:
        warning = (
            "参考稿未标记为 confirmed/gold/manual/aligned，"
            "仅作为诊断，不进入正式 ASR 聚合指标。"
        )

    return {
        "text": text,
        "quality": quality,
        "metadata": metadata,
        "metadata_path": str(metadata_path) if metadata_path else None,
        "use_for_metrics": use_for_metrics,
        "warning": warning,
    }


def _reference_metadata_path(sample: dict[str, Any], reference_path: Path) -> Path | None:
    if sample.get("reference_metadata"):
        return Path(str(sample["reference_metadata"]))
    sidecar = reference_path.with_suffix(".json")
    return sidecar if sidecar.exists() else None


def _load_reference_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _infer_reference_quality(metadata: dict[str, Any]) -> str:
    quality = str(metadata.get("reference_quality") or "").strip().lower()
    if quality:
        return quality
    mode = str(metadata.get("reference_slice_mode") or "").strip().lower()
    if mode in {"time_ratio", "char_ratio", "sentence_ratio"}:
        return f"draft_{mode}"
    if mode == "full":
        return "confirmed"
    return "confirmed"


def _resolve_manifest_path(base_dir: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _baseline_summary(report: dict[str, Any]) -> dict[str, Any]:
    suite = report.get("suite") or {}
    aggregate = report.get("aggregate") or {}
    return {
        "name": suite.get("name") or "N/A",
        "version": suite.get("version"),
        "sample_count": suite.get("sample_count") or aggregate.get("sample_count") or 0,
        "metrics": {
            "mean_cer": ((aggregate.get("asr") or {}).get("mean_cer")),
            "mean_sequence_ratio": ((aggregate.get("asr") or {}).get("mean_sequence_ratio")),
            "mean_hotword_recall": ((aggregate.get("asr") or {}).get("mean_hotword_recall")),
            "mean_speaker_count": ((aggregate.get("speakers") or {}).get("mean_speaker_count")),
            "mean_short_fragment_ratio": (
                (aggregate.get("speakers") or {}).get("mean_short_fragment_ratio")
            ),
            "mean_der": ((aggregate.get("speaker_reference") or {}).get("mean_der")),
            "mean_jer": ((aggregate.get("speaker_reference") or {}).get("mean_jer")),
            "mean_approx_eer": (
                (aggregate.get("voiceprint_threshold_scan") or {}).get("mean_approx_eer")
            ),
            "mean_voiceprint_top1_accuracy": (
                (aggregate.get("voiceprint_identification") or {}).get("mean_top1_accuracy")
            ),
            "mean_voiceprint_topk_accuracy": (
                (aggregate.get("voiceprint_identification") or {}).get("mean_topk_accuracy")
            ),
            "mean_decision_coverage": (
                (aggregate.get("minutes") or {}).get("mean_decision_coverage")
            ),
            "mean_action_item_coverage": (
                (aggregate.get("minutes") or {}).get("mean_action_item_coverage")
            ),
            "mean_risk_coverage": ((aggregate.get("minutes") or {}).get("mean_risk_coverage")),
        },
    }


def _baseline_delta(
    reference: dict[str, Any] | None,
    baseline: dict[str, Any],
) -> dict[str, float | None]:
    if not reference:
        return {}
    reference_metrics = reference.get("metrics") or {}
    baseline_metrics = baseline.get("metrics") or {}
    delta: dict[str, float | None] = {}
    for key, value in baseline_metrics.items():
        reference_value = reference_metrics.get(key)
        delta[key] = (
            float(value) - float(reference_value)
            if value is not None and reference_value is not None
            else None
        )
    return delta


def _available_count(samples: list[dict[str, Any]], section: str) -> int:
    return sum(1 for sample in samples if (sample.get(section) or {}).get("available"))


def _mean_metric(samples: list[dict[str, Any]], section: str, key: str) -> float | None:
    values = [
        float(value)
        for sample in samples
        if (value := (sample.get(section) or {}).get(key)) is not None
    ]
    return sum(values) / len(values) if values else None


def _mean_nested_metric(
    samples: list[dict[str, Any]],
    section: str,
    nested: str,
    key: str,
) -> float | None:
    values = [
        float(value)
        for sample in samples
        if (value := ((sample.get(section) or {}).get(nested) or {}).get(key)) is not None
    ]
    return sum(values) / len(values) if values else None


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
    for reference_label, hypothesis_label in zip(
        reference_labels,
        hypothesis_labels,
        strict=True,
    ):
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
        for reference_label, hypothesis_label in zip(
            reference_labels,
            hypothesis_labels,
            strict=True,
        ):
            mapped_hypothesis = (
                mapping.get(str(hypothesis_label), hypothesis_label)
                if hypothesis_label
                else None
            )
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
            is_match = _voiceprint_candidate_matches(candidate, expected)
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
                    "score": None,
                    "is_match": True,
                    "missing_positive": True,
                }
            )
    return rows


def _voiceprint_candidate_matches(candidate: dict[str, Any], expected: str) -> bool:
    expected_text = str(expected).strip()
    return expected_text in {
        str(candidate.get("profile_id") or "").strip(),
        str(candidate.get("display_name") or "").strip(),
        str(candidate.get("label") or "").strip(),
    }


def _format_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _format_number(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}"


def _format_signed_percent(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:+.2f}%"
