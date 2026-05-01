from __future__ import annotations

import importlib.util
import shutil

from ..api.schemas import AudioDecoderInfo


def get_audio_decoder_info() -> AudioDecoderInfo:
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_available = bool(ffmpeg_path)
    torchaudio_available = importlib.util.find_spec("torchaudio") is not None

    if ffmpeg_available:
        return AudioDecoderInfo(
            backend="ffmpeg",
            ffmpeg_available=True,
            ffmpeg_path=ffmpeg_path,
            torchaudio_available=torchaudio_available,
        )
    if torchaudio_available:
        return AudioDecoderInfo(
            backend="torchaudio",
            ffmpeg_available=False,
            ffmpeg_path=None,
            torchaudio_available=True,
            warning="未检测到 ffmpeg，压缩音频将回退到 torchaudio，MP3/M4A 解码稳定性可能下降。",
        )
    return AudioDecoderInfo(
        backend="none",
        ffmpeg_available=False,
        ffmpeg_path=None,
        torchaudio_available=False,
        warning="未检测到 ffmpeg 或 torchaudio，压缩音频不可稳定解码；请安装 ffmpeg。",
    )
