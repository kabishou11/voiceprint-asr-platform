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
    build_baseline_comparison_report,
    load_baseline_report,
    render_baseline_comparison_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="对比多个核心流水线样本集 baseline JSON。")
    parser.add_argument("baselines", nargs="+", help="evaluate_core_pipeline_dataset.py 生成的 baseline JSON")
    parser.add_argument("--comparison-name", default="core_pipeline_baseline_comparison", help="输出目录名")
    parser.add_argument("--output-json", default=None, help="输出 JSON 对比报告路径")
    parser.add_argument("--output-markdown", default=None, help="输出 Markdown 对比报告路径")
    args = parser.parse_args()

    baseline_paths = [Path(path).resolve() for path in args.baselines]
    report = build_baseline_comparison_report([load_baseline_report(path) for path in baseline_paths])
    report["inputs"] = {"baselines": [str(path) for path in baseline_paths]}

    artifact_dir = ensure_artifact_dir(args.comparison_name)
    output_json = (
        Path(args.output_json)
        if args.output_json
        else artifact_dir / f"{args.comparison_name}.json"
    )
    output_markdown = (
        Path(args.output_markdown)
        if args.output_markdown
        else artifact_dir / f"{args.comparison_name}.md"
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown.write_text(render_baseline_comparison_markdown(report), encoding="utf-8")
    print(f"JSON comparison: {output_json}")
    print(f"Markdown comparison: {output_markdown}")


if __name__ == "__main__":
    main()
