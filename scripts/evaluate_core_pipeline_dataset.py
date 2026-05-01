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
    build_core_pipeline_dataset_report,
    load_dataset_manifest,
    render_dataset_markdown_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="批量评测核心流水线样本集，输出可横向比较的基线报告。")
    parser.add_argument("manifest", help="样本集 manifest JSON")
    parser.add_argument("--suite-name", default=None, help="输出目录名，默认使用 manifest 中的 suite_name")
    parser.add_argument("--output-json", default=None, help="输出 JSON 基线报告路径")
    parser.add_argument("--output-markdown", default=None, help="输出 Markdown 基线报告路径")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.65, help="声纹低置信阈值")
    parser.add_argument("--speaker-frame-step-ms", type=int, default=100, help="DER/JER 近似采样步长")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_dataset_manifest(manifest_path)
    report = build_core_pipeline_dataset_report(
        manifest,
        low_confidence_threshold=args.low_confidence_threshold,
        speaker_frame_step_ms=args.speaker_frame_step_ms,
    )
    report["inputs"] = {"manifest": str(manifest_path)}

    suite_name = args.suite_name or str(report["suite"].get("name") or manifest_path.stem)
    artifact_dir = ensure_artifact_dir(suite_name)
    output_json = Path(args.output_json) if args.output_json else artifact_dir / f"{suite_name}_baseline.json"
    output_markdown = (
        Path(args.output_markdown)
        if args.output_markdown
        else artifact_dir / f"{suite_name}_baseline.md"
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown.write_text(render_dataset_markdown_report(report), encoding="utf-8")
    print(f"JSON baseline: {output_json}")
    print(f"Markdown baseline: {output_markdown}")


if __name__ == "__main__":
    main()
