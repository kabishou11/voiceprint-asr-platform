from __future__ import annotations

import hashlib
from pathlib import Path

from model_adapters import AudioAsset


# 所有 FunASR 支持的音频格式
SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".flac", ".ogg",
    ".aac", ".opus", ".wma", ".ape", ".ac3",
    ".mp4", ".avi", ".mov", ".mkv",  # 视频格式由 ffmpeg 处理
}


def detect_audio_format(path: str) -> str:
    """检测音频格式，基于文件扩展名。"""
    suffix = Path(path).suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return suffix
    # 尝试根据文件魔数判断
    try:
        with open(path, "rb") as f:
            header = f.read(12)
        if header[:4] == b"RIFF" and header[8:12] in (b"WAVE", b"fmt "):
            return ".wav"
        if header[:3] == b"ID3" or (header[0] & 0xFF) == 0xFF:
            return ".mp3"
        if header[:4] == b"\xff\xfb" or header[:4] == b"\xff\xf3":
            return ".mp3"
        if header[:4] == b"fLaC":
            return ".flac"
        if header[:4] == b"OggS":
            return ".ogg"
    except Exception:
        pass
    return ".wav"  # 默认当 WAV 处理


def preprocess_audio(asset: AudioAsset) -> AudioAsset:
    """预处理音频，自动检测采样率并标准化为 16kHz 单声道。

    支持的格式：WAV, MP3, M4A, FLAC, OGG, AAC, OPUS 等
    （压缩格式依赖 librosa/ffmpeg 自动解码）

    流程：
    1. 检测音频格式
    2. 解码为 PCM
    3. 重采样为 16kHz（如需要）
    4. 转换为单声道（如需要）
    """
    source = Path(asset.path)
    if not source.exists():
        return AudioAsset(path=asset.path, sample_rate=16000, channels=1)

    try:
        import librosa
        import numpy as np
        import soundfile as sf
    except Exception:
        return AudioAsset(path=asset.path, sample_rate=16000, channels=1)

    processed_dir = Path("storage/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha1(f"{source.resolve()}:{source.stat().st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    target = processed_dir / f"{source.stem}-{fingerprint}.wav"
    if target.exists():
        return AudioAsset(path=str(target), sample_rate=16000, channels=1)

    suffix = source.suffix.lower()
    if suffix == ".wav":
        audio, sample_rate = sf.read(source, dtype="float32", always_2d=False)
    else:
        audio, sample_rate = librosa.load(str(source), sr=None, mono=False)

    audio = np.asarray(audio, dtype=np.float32)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=0 if audio.shape[0] <= 8 else 1)
    if sample_rate != 16000:
        audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / max(peak, 1e-6) * 0.95

    sf.write(target, audio, 16000)
    return AudioAsset(path=str(target), sample_rate=16000, channels=1)


def validate_audio_asset(path: str) -> tuple[bool, str]:
    """验证音频文件是否有效，返回 (是否有效, 错误信息)。"""
    p = Path(path)
    if not p.exists():
        return False, "文件不存在"
    if p.stat().st_size == 0:
        return False, "文件为空"
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False, f"不支持的音频格式: {suffix}，支持: WAV/MP3/M4A/FLAC/OGG/AAC/OPUS"
    # 大小限制：最大 2GB
    if p.stat().st_size > 2 * 1024 * 1024 * 1024:
        return False, "文件过大，最大支持 2GB"
    return True, ""
