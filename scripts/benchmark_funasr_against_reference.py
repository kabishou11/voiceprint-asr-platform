from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for extra in (
    ROOT / "packages/python/domain/src",
    ROOT / "packages/python/model_adapters/src",
):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from domain.schemas.transcript import TranscriptResult
from model_adapters import AudioAsset
from model_adapters.funasr_adapter import FunASRTranscribeAdapter
from scripts.artifact_paths import resolve_artifact_path


def load_hotwords(path: str | None) -> list[str]:
    if not path:
        return []
    payload = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in payload.splitlines() if line.strip()]


def normalize_compare_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"file:\s*.*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*+result\*+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[，。！？；：、“”‘’,.!?;:~\-—_\(\)\[\]{}<>]", "", cleaned)
    return cleaned


def _duration_seconds(audio_path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(audio_path))
    if not info.samplerate:
        return 0.0
    return float(info.frames) / float(info.samplerate)


def _slice_audio_for_benchmark(audio_path: Path, max_seconds: float) -> Path:
    import soundfile as sf

    audio, sample_rate = sf.read(str(audio_path), dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    max_samples = max(1, int(sample_rate * max_seconds))
    clipped = audio[:max_samples]
    handle = tempfile.NamedTemporaryFile(prefix="funasr-bench-", suffix=".wav", delete=False)
    handle.close()
    temp_path = Path(handle.name)
    sf.write(str(temp_path), clipped, sample_rate)
    return temp_path


def _split_reference_units(text: str) -> list[str]:
    units = [part for part in re.split(r"(?<=[。！？；!?;])", text) if part]
    if units:
        return units
    stripped = text.strip()
    return [stripped] if stripped else []


def _slice_reference_text_for_benchmark(
    text: str,
    *,
    audio_duration_seconds: float,
    max_seconds: float | None,
) -> tuple[str, dict[str, float | int | str | None]]:
    payload = text or ""
    if not payload.strip():
        return payload, {
            "reference_slice_mode": "empty",
            "reference_slice_ratio": 0.0,
            "reference_full_length": 0,
            "reference_slice_length": 0,
        }
    if max_seconds is None or max_seconds <= 0 or audio_duration_seconds <= 0 or max_seconds >= audio_duration_seconds:
        return payload, {
            "reference_slice_mode": "full",
            "reference_slice_ratio": 1.0,
            "reference_full_length": len(payload),
            "reference_slice_length": len(payload),
        }

    ratio = max(0.0, min(1.0, float(max_seconds) / float(audio_duration_seconds)))
    units = _split_reference_units(payload)
    if len(units) <= 1:
        slice_len = max(1, int(round(len(payload) * ratio)))
        sliced = payload[:slice_len]
        return sliced, {
            "reference_slice_mode": "char_ratio",
            "reference_slice_ratio": ratio,
            "reference_full_length": len(payload),
            "reference_slice_length": len(sliced),
        }

    total_chars = max(1, sum(len(unit) for unit in units))
    target_chars = max(1, int(round(total_chars * ratio)))
    collected: list[str] = []
    collected_chars = 0
    for unit in units:
        collected.append(unit)
        collected_chars += len(unit)
        if collected_chars >= target_chars:
            break
    sliced = "".join(collected).strip()
    return sliced, {
        "reference_slice_mode": "sentence_ratio",
        "reference_slice_ratio": ratio,
        "reference_full_length": len(payload),
        "reference_slice_length": len(sliced),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="使用 FunASR + 热词跑样本，并与参考稿做轻量对比。")
    parser.add_argument("audio", help="输入音频路径")
    parser.add_argument("output_json", nargs="?", default=None, help="输出 TranscriptResult JSON")
    parser.add_argument("--output-text", default=None, help="输出纯文本路径")
    parser.add_argument("--hotwords-file", default=None, help="热词文件路径")
    parser.add_argument("--reference-text", default=None, help="参考文本路径")
    parser.add_argument("--language", default="zh-cn", help="语言")
    parser.add_argument("--max-seconds", type=float, default=None, help="只跑前 N 秒音频，便于快速 benchmark")
    args = parser.parse_args()

    hotwords = load_hotwords(args.hotwords_file)
    adapter = FunASRTranscribeAdapter(
        hotwords=hotwords,
        language=args.language,
        vad_enabled=True,
        itn=True,
    )
    audio_path = Path(args.audio).resolve()
    original_audio_duration = _duration_seconds(audio_path)
    temp_audio_path: Path | None = None
    if args.max_seconds and args.max_seconds > 0:
        temp_audio_path = _slice_audio_for_benchmark(audio_path, float(args.max_seconds))
        audio_path = temp_audio_path
    asset = AudioAsset(path=str(audio_path), sample_rate=16000)
    try:
        result = adapter.transcribe(asset)
    finally:
        if temp_audio_path is not None and temp_audio_path.exists():
            temp_audio_path.unlink(missing_ok=True)

    sample_key = Path(args.audio).stem
    output_json = (
        Path(args.output_json)
        if args.output_json
        else resolve_artifact_path(sample_key, f"{sample_key}_funasr.json")
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if args.output_text:
        Path(args.output_text).write_text(result.text, encoding="utf-8")
    elif result.text:
        resolve_artifact_path(sample_key, f"{sample_key}_funasr.txt").write_text(result.text, encoding="utf-8")

    if args.reference_text:
        reference_payload = Path(args.reference_text).read_text(encoding="utf-8")
        sliced_reference, slice_meta = _slice_reference_text_for_benchmark(
            reference_payload,
            audio_duration_seconds=original_audio_duration,
            max_seconds=args.max_seconds,
        )
        ratio = difflib.SequenceMatcher(
            a=normalize_compare_text(sliced_reference),
            b=normalize_compare_text(result.text),
        ).ratio()
        report_path = output_json.with_suffix(".benchmark.json")
        report_path.write_text(
            json.dumps(
                {
                    "audio": str(Path(args.audio).resolve()),
                    "benchmarked_audio": str(audio_path),
                    "reference_text": str(Path(args.reference_text).resolve()),
                    "hotwords_count": len(hotwords),
                    "sequence_ratio": ratio,
                    "max_seconds": args.max_seconds,
                    **slice_meta,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
