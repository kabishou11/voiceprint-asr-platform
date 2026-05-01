from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core_pipeline_metrics import TranscriptArtifact, TranscriptSegment, load_transcript_artifact


def build_annotation_templates(
    transcript: TranscriptArtifact,
    *,
    sample_id: str,
) -> dict[str, str]:
    speakers = _speaker_order(transcript.segments)
    return {
        "rttm": render_rttm_template(transcript.segments, sample_id=sample_id),
        "voiceprint_labels": json.dumps(
            {
                "speakers": {
                    speaker: {
                        "profile_id": "",
                        "display_name": "",
                        "notes": "TODO: 人工填写该 speaker 对应的声纹 profile_id；不确定则保留空值。",
                    }
                    for speaker in speakers
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "minutes": json.dumps(
            {
                "decisions": [],
                "action_items": [],
                "risks": [],
                "notes": "TODO: 人工从参考纪要或会议复核结果中填写，用于覆盖率评测。",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "review_notes": render_review_notes(transcript, speakers=speakers, sample_id=sample_id),
    }


def render_rttm_template(segments: list[TranscriptSegment], *, sample_id: str) -> str:
    lines = [
        "# Draft RTTM generated from current transcript speaker segments.",
        "# Review and correct speaker boundaries/labels before using as reference_speakers.",
    ]
    for segment in segments:
        if not segment.speaker or segment.end_ms <= segment.start_ms:
            continue
        start_seconds = segment.start_ms / 1000.0
        duration_seconds = (segment.end_ms - segment.start_ms) / 1000.0
        lines.append(
            " ".join(
                [
                    "SPEAKER",
                    sample_id,
                    "1",
                    f"{start_seconds:.3f}",
                    f"{duration_seconds:.3f}",
                    "<NA>",
                    "<NA>",
                    segment.speaker,
                    "<NA>",
                    "<NA>",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def render_review_notes(
    transcript: TranscriptArtifact,
    *,
    speakers: list[str],
    sample_id: str,
) -> str:
    speaker_durations = _speaker_durations(transcript.segments)
    lines = [
        f"# {sample_id} 评测标注复核清单",
        "",
        "这些文件是从当前模型转写结果生成的草稿，不应直接当作人工真值。",
        "",
        "## Speaker 草稿",
    ]
    for speaker in speakers:
        lines.append(f"- {speaker}: {_format_duration_ms(speaker_durations.get(speaker, 0))}")
    lines.extend(
        [
            "",
            "## 人工复核步骤",
            "1. 打开 RTTM 草稿，修正 speaker 边界和 speaker 标签。",
            "2. 在 voiceprint labels JSON 中填写每个 speaker 对应的 profile_id。",
            "3. 在 minutes JSON 中填写人工确认的决策、行动项和风险。",
            "4. 复核完成后，把 manifest 中的 reference_speakers、voiceprint_labels、minutes_json 指向这些已确认文件。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_annotation_templates(
    templates: dict[str, str],
    *,
    output_dir: Path,
    prefix: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "rttm": output_dir / f"{prefix}_reference_speakers.draft.rttm",
        "voiceprint_labels": output_dir / f"{prefix}_voiceprint_labels.draft.json",
        "minutes": output_dir / f"{prefix}_minutes_baseline.draft.json",
        "review_notes": output_dir / f"{prefix}_annotation_review.md",
    }
    for key, path in targets.items():
        path.write_text(templates[key], encoding="utf-8")
    return {key: str(path) for key, path in targets.items()}


def _speaker_order(segments: list[TranscriptSegment]) -> list[str]:
    speakers: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        if not segment.speaker or segment.speaker in seen:
            continue
        speakers.append(segment.speaker)
        seen.add(segment.speaker)
    return speakers


def _speaker_durations(segments: list[TranscriptSegment]) -> dict[str, int]:
    durations: dict[str, int] = {}
    for segment in segments:
        if not segment.speaker:
            continue
        durations[segment.speaker] = durations.get(segment.speaker, 0) + max(
            0,
            segment.end_ms - segment.start_ms,
        )
    return durations


def _format_duration_ms(duration_ms: int) -> str:
    seconds = max(0, int(round(duration_ms / 1000)))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="从转写结果生成评测人工标注草稿模板。")
    parser.add_argument("transcript", help="TranscriptResult JSON 或 readable txt 转写产物")
    parser.add_argument("--sample-id", default=None, help="RTTM file-id，默认取 transcript 文件名")
    parser.add_argument("--output-dir", required=True, help="模板输出目录")
    parser.add_argument("--prefix", default=None, help="模板文件名前缀，默认使用 sample-id")
    args = parser.parse_args()

    transcript_path = Path(args.transcript).resolve()
    sample_id = args.sample_id or transcript_path.stem
    prefix = args.prefix or sample_id
    templates = build_annotation_templates(
        load_transcript_artifact(transcript_path),
        sample_id=sample_id,
    )
    outputs = write_annotation_templates(
        templates,
        output_dir=Path(args.output_dir),
        prefix=prefix,
    )
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
