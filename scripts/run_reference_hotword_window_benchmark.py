from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.artifact_paths import ensure_artifact_dir
from scripts.benchmark_funasr_against_reference import main as benchmark_main
from scripts.extract_hotwords_from_reference import (
    extract_hotwords,
    normalize_reference_text,
    slice_reference_text_by_ratio,
)


def _audio_duration_seconds(audio_path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(audio_path))
    if not info.samplerate:
        return 0.0
    return float(info.frames) / float(info.samplerate)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_benchmark_cli(args: list[str]) -> None:
    previous_argv = sys.argv[:]
    try:
        sys.argv = ["benchmark_funasr_against_reference.py", *args]
        benchmark_main()
    finally:
        sys.argv = previous_argv


def _build_summary_payload(
    *,
    audio: Path,
    reference_text: Path,
    window_seconds: float,
    hotwords: list[str],
    baseline_report: dict,
    hotword_report: dict,
) -> dict:
    baseline_ratio = baseline_report.get("sequence_ratio")
    hotword_ratio = hotword_report.get("sequence_ratio")
    return {
        "audio": str(audio),
        "reference_text": str(reference_text),
        "window_seconds": window_seconds,
        "hotwords": hotwords,
        "baseline_ratio": baseline_ratio,
        "hotword_ratio": hotword_ratio,
        "ratio_delta": (hotword_ratio or 0.0) - (baseline_ratio or 0.0),
        "baseline_report": baseline_report.get("_path"),
        "hotword_report": hotword_report.get("_path"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="按同一时间窗执行参考稿热词提取与 FunASR benchmark。")
    parser.add_argument("audio", help="输入音频路径")
    parser.add_argument("--reference-text", required=True, help="参考转写稿路径")
    parser.add_argument("--sample-name", default=None, help="产物目录名，默认取音频文件名")
    parser.add_argument("--window-seconds", type=float, default=900.0, help="评测窗口长度，默认 15 分钟")
    parser.add_argument("--hotword-limit", type=int, default=12, help="最多热词数")
    parser.add_argument("--language", default="zh-cn", help="语言")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    sample_name = args.sample_name or audio_path.stem
    artifact_dir = ensure_artifact_dir(sample_name)

    baseline_json = artifact_dir / f"{sample_name}_window_baseline.json"
    baseline_txt = artifact_dir / f"{sample_name}_window_baseline.txt"
    baseline_benchmark = artifact_dir / f"{sample_name}_window_baseline.benchmark.json"

    _run_benchmark_cli(
        [
            str(audio_path),
            str(baseline_json),
            "--output-text",
            str(baseline_txt),
            "--reference-text",
            str(Path(args.reference_text).resolve()),
            "--language",
            args.language,
            "--max-seconds",
            str(args.window_seconds),
        ]
    )

    reference_payload = Path(args.reference_text).read_text(encoding="utf-8")
    audio_duration_seconds = _audio_duration_seconds(audio_path)
    sliced_reference = slice_reference_text_by_ratio(
        reference_payload,
        audio_duration_seconds=audio_duration_seconds,
        max_seconds=args.window_seconds,
    )
    baseline_text = baseline_txt.read_text(encoding="utf-8")
    hotwords = extract_hotwords(
        normalize_reference_text(sliced_reference),
        limit=args.hotword_limit,
        baseline_text=baseline_text,
    )
    hotword_path = artifact_dir / f"{sample_name}_window_hotwords.txt"
    _write_text(hotword_path, "\n".join(hotwords) + ("\n" if hotwords else ""))

    hotword_json = artifact_dir / f"{sample_name}_window_hotwords.json"
    hotword_txt = artifact_dir / f"{sample_name}_window_hotword_result.txt"
    hotword_benchmark = artifact_dir / f"{sample_name}_window_hotwords.benchmark.json"

    _run_benchmark_cli(
        [
            str(audio_path),
            str(hotword_json),
            "--output-text",
            str(hotword_txt),
            "--reference-text",
            str(Path(args.reference_text).resolve()),
            "--hotwords-file",
            str(hotword_path),
            "--language",
            args.language,
            "--max-seconds",
            str(args.window_seconds),
        ]
    )

    baseline_report = _load_json(baseline_benchmark)
    hotword_report = _load_json(hotword_benchmark)
    baseline_report["_path"] = str(baseline_benchmark)
    hotword_report["_path"] = str(hotword_benchmark)
    summary = _build_summary_payload(
        audio=audio_path,
        reference_text=Path(args.reference_text).resolve(),
        window_seconds=args.window_seconds,
        hotwords=hotwords,
        baseline_report=baseline_report,
        hotword_report=hotword_report,
    )
    summary_path = artifact_dir / f"{sample_name}_window_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
