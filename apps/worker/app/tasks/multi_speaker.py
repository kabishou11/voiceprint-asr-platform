from __future__ import annotations

from domain.schemas.transcript import TranscriptMetadata, TranscriptResult, TranscriptTimeline
from model_adapters import resolve_audio_asset_path

from ..pipelines.alignment import (
    align_transcript_with_speakers,
    build_display_speaker_timeline,
    build_exclusive_speaker_timeline,
)
from ..pipelines.audio_preprocess import preprocess_audio
from ..worker_runtime import get_worker_registry


def run_multi_speaker_transcription(
    job_id: str,
    asset_name: str,
    asr_model_key: str = "funasr-nano",
    diarization_model_key: str = "3dspeaker-diarization",
    *,
    hotwords: list[str] | None = None,
    language: str = "zh-cn",
    vad_enabled: bool = True,
    itn: bool = True,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> TranscriptResult:
    """运行多人转写任务。

    参数：
        job_id: 任务 ID
        asset_name: 音频资产名
        asr_model_key: ASR 模型键（默认 funasr-nano）
        diarization_model_key: 说话人分离模型键（默认 3dspeaker-diarization）
        hotwords: 热词列表，用于提升专业术语识别率
        language: 语言/方言（zh-cn / en / yue / Sichuan 等）
        vad_enabled: 是否启用 VAD（语音活动检测，过滤静音噪声）
        itn: 是否启用逆文本正则化（数字/日期/货币格式化）
        num_speakers: 已知说话人数量（用于聚类提示，None 则自动估计）
    """
    registry = get_worker_registry()
    registry.require_available(asr_model_key)
    registry.require_available(diarization_model_key)
    asset = preprocess_audio(adapter_asset(asset_name))

    # 配置 ASR 适配器
    asr_adapter = registry.get_asr(asr_model_key)
    if hotwords and hasattr(asr_adapter, "hotwords"):
        asr_adapter.hotwords = hotwords
    if hasattr(asr_adapter, "language"):
        asr_adapter.language = language
    if hasattr(asr_adapter, "vad_enabled"):
        asr_adapter.vad_enabled = vad_enabled
    if hasattr(asr_adapter, "itn"):
        asr_adapter.itn = itn

    # 运行 ASR 转写
    transcript = asr_adapter.transcribe(asset)

    # 运行说话人分离（VAD + CAM++ + 谱聚类）
    diarization_adapter = registry.get_diarization(diarization_model_key)
    if hasattr(diarization_adapter, "num_speakers"):
        diarization_adapter.num_speakers = num_speakers
    if hasattr(diarization_adapter, "min_speakers"):
        diarization_adapter.min_speakers = min_speakers
    if hasattr(diarization_adapter, "max_speakers"):
        diarization_adapter.max_speakers = max_speakers
    diarization_segments = diarization_adapter.diarize(asset)

    # 对齐转写文本与说话人标签
    aligned = align_transcript_with_speakers(transcript, diarization_segments)
    exclusive_segments = build_exclusive_speaker_timeline(diarization_segments)
    display_segments = build_display_speaker_timeline(aligned.segments, exclusive_segments or diarization_segments)
    metadata = TranscriptMetadata(
        diarization_model=diarization_model_key,
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
    return aligned.model_copy(update={"metadata": metadata})


def adapter_asset(asset_name: str):
    from model_adapters import AudioAsset

    return AudioAsset(path=resolve_audio_asset_path(asset_name))
