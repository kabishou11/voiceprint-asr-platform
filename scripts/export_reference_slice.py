from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extract_hotwords_from_reference import slice_reference_text_by_ratio


def build_reference_slice(
    reference_text: str,
    *,
    audio_duration_seconds: float,
    max_seconds: float | None,
) -> tuple[str, dict[str, float | int | str | None]]:
    sliced = slice_reference_text_by_ratio(
        reference_text,
        audio_duration_seconds=audio_duration_seconds,
        max_seconds=max_seconds,
    )
    if not reference_text.strip():
        mode = "empty"
        ratio = 0.0
    elif (
        max_seconds is None
        or max_seconds <= 0
        or audio_duration_seconds <= 0
        or max_seconds >= audio_duration_seconds
    ):
        mode = "full"
        ratio = 1.0
    else:
        mode = "time_ratio"
        ratio = max(0.0, min(1.0, float(max_seconds) / float(audio_duration_seconds)))

    return sliced, {
        "reference_slice_mode": mode,
        "reference_slice_ratio": ratio,
        "reference_quality": f"draft_{mode}" if mode == "time_ratio" else "confirmed",
        "audio_duration_seconds": audio_duration_seconds,
        "max_seconds": max_seconds,
        "reference_full_length": len(reference_text),
        "reference_slice_length": len(sliced),
    }


def audio_duration_seconds(audio_path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(audio_path))
    if not info.samplerate:
        return 0.0
    return float(info.frames) / float(info.samplerate)


def main() -> None:
    parser = argparse.ArgumentParser(description="按音频时间窗导出固定参考稿切片。")
    parser.add_argument("reference_text", help="完整参考稿路径")
    parser.add_argument("output_text", help="输出参考稿切片路径")
    parser.add_argument("--audio", required=True, help="对应完整音频路径，用于计算切片比例")
    parser.add_argument("--max-seconds", type=float, default=900.0, help="切片窗口秒数")
    parser.add_argument("--metadata-json", default=None, help="输出切片元数据 JSON")
    args = parser.parse_args()

    reference_path = Path(args.reference_text).resolve()
    audio_path = Path(args.audio).resolve()
    output_path = Path(args.output_text)
    sliced, metadata = build_reference_slice(
        reference_path.read_text(encoding="utf-8"),
        audio_duration_seconds=audio_duration_seconds(audio_path),
        max_seconds=args.max_seconds,
    )
    metadata.update(
        {
            "reference_text": str(reference_path),
            "audio": str(audio_path),
            "output_text": str(output_path.resolve()),
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sliced, encoding="utf-8")
    if args.metadata_json:
        metadata_path = Path(args.metadata_json)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Reference slice: {output_path}")
    if args.metadata_json:
        print(f"Metadata: {args.metadata_json}")


if __name__ == "__main__":
    main()
