from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.artifact_paths import ensure_artifact_dir
from scripts.core_pipeline_metrics import (
    build_core_pipeline_report,
    load_hotwords,
    load_minutes_payload,
    load_speaker_reference,
    load_transcript_artifact,
    load_voiceprint_labels,
    render_markdown_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="评测核心流水线产物，输出 ASR/Speaker/声纹/纪要诊断报告。")
    parser.add_argument("transcript", help="TranscriptResult JSON 或 readable txt 转写产物")
    parser.add_argument("--reference-text", default=None, help="参考文本路径，用于 CER/相似度")
    parser.add_argument("--reference-speakers", default=None, help="speaker 标注文件，支持 RTTM、TranscriptResult JSON 或 readable txt")
    parser.add_argument("--hotwords-file", default=None, help="热词文件，支持 txt 或 {hotwords: []} JSON")
    parser.add_argument("--minutes-json", default=None, help="会议纪要 JSON，用于覆盖率诊断")
    parser.add_argument("--voiceprint-labels", default=None, help="声纹真值 JSON，格式为 {speaker: profile_id}")
    parser.add_argument("--sample-name", default=None, help="输出目录名，默认使用 transcript 文件名")
    parser.add_argument("--output-json", default=None, help="输出 JSON 报告路径")
    parser.add_argument("--output-markdown", default=None, help="输出 Markdown 报告路径")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.65, help="声纹低置信阈值")
    parser.add_argument("--speaker-frame-step-ms", type=int, default=100, help="DER/JER 近似采样步长")
    args = parser.parse_args()

    transcript_path = Path(args.transcript).resolve()
    transcript = load_transcript_artifact(transcript_path)
    reference_text = (
        Path(args.reference_text).read_text(encoding="utf-8")
        if args.reference_text
        else None
    )
    report = build_core_pipeline_report(
        transcript=transcript,
        reference_text=reference_text,
        reference_speaker_segments=load_speaker_reference(args.reference_speakers),
        hotwords=load_hotwords(args.hotwords_file),
        minutes_payload=load_minutes_payload(args.minutes_json),
        low_confidence_threshold=args.low_confidence_threshold,
        voiceprint_ground_truth=load_voiceprint_labels(args.voiceprint_labels),
        speaker_frame_step_ms=args.speaker_frame_step_ms,
    )
    report["inputs"] = {
        "transcript": str(transcript_path),
        "reference_text": str(Path(args.reference_text).resolve()) if args.reference_text else None,
        "reference_speakers": str(Path(args.reference_speakers).resolve()) if args.reference_speakers else None,
        "hotwords_file": str(Path(args.hotwords_file).resolve()) if args.hotwords_file else None,
        "minutes_json": str(Path(args.minutes_json).resolve()) if args.minutes_json else None,
        "voiceprint_labels": str(Path(args.voiceprint_labels).resolve()) if args.voiceprint_labels else None,
    }

    sample_name = args.sample_name or transcript_path.stem
    artifact_dir = ensure_artifact_dir(sample_name)
    output_json = Path(args.output_json) if args.output_json else artifact_dir / f"{sample_name}_evaluation.json"
    output_markdown = (
        Path(args.output_markdown)
        if args.output_markdown
        else artifact_dir / f"{sample_name}_evaluation.md"
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"JSON report: {output_json}")
    print(f"Markdown report: {output_markdown}")


if __name__ == "__main__":
    main()
