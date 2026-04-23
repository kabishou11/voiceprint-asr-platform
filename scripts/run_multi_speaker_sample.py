from __future__ import annotations

import argparse
import sys
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

from apps.worker.app.tasks.multi_speaker import run_multi_speaker_transcription
from apps.worker.app.pipelines.alignment import (
    align_transcript_with_speakers,
    build_display_speaker_timeline,
    build_exclusive_speaker_timeline,
)
from apps.worker.app.pipelines.audio_preprocess import preprocess_audio
from apps.worker.app.worker_runtime import get_worker_registry
from domain.schemas.transcript import TranscriptMetadata, TranscriptTimeline
from model_adapters import AudioAsset
from scripts.artifact_paths import resolve_artifact_path
from scripts.export_readable_transcript import render_readable_transcript


def main() -> None:
    parser = argparse.ArgumentParser(description="运行多人转写样本并导出 JSON/可读稿。")
    parser.add_argument("asset_name", help="音频资产名或可解析路径")
    parser.add_argument("output_json", nargs="?", default=None, help="输出 TranscriptResult JSON 路径")
    parser.add_argument("--output-text", default=None, help="输出可读文本路径")
    parser.add_argument("--title", default=None, help="导出标题")
    parser.add_argument("--language", default="zh-cn", help="语言")
    parser.add_argument("--num-speakers", type=int, default=None, help="已知说话人数")
    parser.add_argument("--min-speakers", type=int, default=None, help="最少说话人数")
    parser.add_argument("--max-speakers", type=int, default=None, help="最多说话人数")
    parser.add_argument("--hotwords-file", default=None, help="热词文件路径")
    args = parser.parse_args()

    hotwords: list[str] | None = None
    if args.hotwords_file:
        hotwords = [
            line.strip()
            for line in Path(args.hotwords_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    asset_candidate = Path(args.asset_name)
    if asset_candidate.exists():
        registry = get_worker_registry()
        asr_adapter = registry.get_asr("funasr-nano")
        diarization_adapter = registry.get_diarization("3dspeaker-diarization")
        if hotwords and hasattr(asr_adapter, "hotwords"):
            asr_adapter.hotwords = hotwords
        if hasattr(asr_adapter, "language"):
            asr_adapter.language = args.language
        if hasattr(asr_adapter, "vad_enabled"):
            asr_adapter.vad_enabled = True
        if hasattr(asr_adapter, "itn"):
            asr_adapter.itn = True
        if hasattr(diarization_adapter, "num_speakers"):
            diarization_adapter.num_speakers = args.num_speakers
        if hasattr(diarization_adapter, "min_speakers"):
            diarization_adapter.min_speakers = args.min_speakers
        if hasattr(diarization_adapter, "max_speakers"):
            diarization_adapter.max_speakers = args.max_speakers

        asset = preprocess_audio(AudioAsset(path=str(asset_candidate.resolve())))
        transcript = asr_adapter.transcribe(asset)
        diarization_segments = diarization_adapter.diarize(asset)
        exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)
        aligned = align_transcript_with_speakers(transcript, diarization_segments)
        display_segments = build_display_speaker_timeline(
            aligned.segments,
            exclusive_segments or diarization_segments,
        )
        result = aligned.model_copy(
            update={
                "metadata": TranscriptMetadata(
                    diarization_model="3dspeaker-diarization",
                    alignment_source="exclusive" if exclusive_segments else "regular",
                    timelines=[
                        TranscriptTimeline(label="Regular diarization", source="regular", segments=diarization_segments),
                        TranscriptTimeline(
                            label="Exclusive alignment timeline",
                            source="exclusive",
                            segments=exclusive_segments or diarization_segments,
                        ),
                        TranscriptTimeline(
                            label="Display speaker timeline",
                            source="display",
                            segments=display_segments,
                        ),
                    ],
                )
            }
        )
    else:
        result = run_multi_speaker_transcription(
            job_id="sample-run",
            asset_name=args.asset_name,
            hotwords=hotwords,
            language=args.language,
            vad_enabled=True,
            itn=True,
            num_speakers=args.num_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
        )

    sample_key = Path(args.asset_name).stem
    output_json = (
        Path(args.output_json)
        if args.output_json
        else resolve_artifact_path(sample_key, f"{sample_key}_multispeaker.json")
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    output_text = (
        Path(args.output_text)
        if args.output_text
        else resolve_artifact_path(sample_key, f"{sample_key}_multispeaker_readable.txt")
    )
    output_text.parent.mkdir(parents=True, exist_ok=True)
    output_text.write_text(
            render_readable_transcript(
                result,
                title=args.title or Path(args.asset_name).name,
                include_full_text=False,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
