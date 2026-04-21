from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np

from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters.base import ASRAdapter, AudioAsset, resolve_model_reference


class FunASRTranscribeAdapter(ASRAdapter):
    key = "funasr-nano"
    display_name = "FunASR Nano"
    provider = "funasr"

    def __init__(self, model_name: str = "FunAudioLLM/Fun-ASR-Nano-2512") -> None:
        self.model_name = resolve_model_reference(model_name)
        self._auto_model_cls: Any | None = None
        self._model: Any | None = None
        self._backend_checked = False

    @property
    def availability(self) -> str:
        return "available" if self._ensure_backend() else "optional"

    def _ensure_backend(self) -> bool:
        if self._auto_model_cls is not None:
            return True
        if self._backend_checked:
            return False
        self._backend_checked = True
        if importlib.util.find_spec("funasr") is None:
            return False
        from funasr import AutoModel

        self._auto_model_cls = AutoModel
        return True

    def _resolve_device(self) -> str:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        if not self._ensure_backend():
            return None
        model_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "trust_remote_code": True,
            "device": self._resolve_device(),
        }
        if Path(self.model_name).exists():
            remote_code = Path(__file__).with_name("funasr_nano_remote.py")
            model_kwargs.update(
                {
                    "remote_code": remote_code.as_posix(),
                    "disable_update": True,
                }
            )
        self._model = self._auto_model_cls(**model_kwargs)
        return self._model

    def _load_audio_input(self, asset: AudioAsset) -> Any:
        import torch

        suffix = Path(asset.path).suffix.lower()
        if suffix == ".wav":
            import soundfile as sf

            audio, sample_rate = sf.read(asset.path, dtype="float32", always_2d=False)
            if getattr(audio, "ndim", 1) > 1:
                audio = audio.mean(axis=1)
            if sample_rate != asset.sample_rate:
                import librosa

                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=asset.sample_rate)
            return torch.from_numpy(np.asarray(audio, dtype=np.float32))

        if suffix in {".m4a", ".mp3", ".flac"}:
            try:
                import librosa

                audio, _ = librosa.load(asset.path, sr=asset.sample_rate, mono=True)
                return torch.from_numpy(np.asarray(audio, dtype=np.float32))
            except Exception as exc:
                raise RuntimeError(
                    f"无法解码音频文件 {asset.path}。当前环境缺少可用的压缩音频解码后端；请安装 ffmpeg，或先将文件转为 16k WAV。"
                ) from exc

        return asset.path

    def transcribe(self, asset: AudioAsset) -> TranscriptResult:
        model = self._load_model()
        if model is None:
            return self._fallback_result(asset)
        audio_input = self._load_audio_input(asset)
        result = model.generate(input=audio_input, cache={}, batch_size=1, language="中文", itn=True)
        return self._normalize_result(result)

    def _fallback_result(self, asset: AudioAsset) -> TranscriptResult:
        text = f"[{self.model_name}] 已接收音频 {asset.path}，当前使用占位输出，待接入 FunASR AutoModel 真正推理。"
        return TranscriptResult(
            text=text,
            language="zh",
            segments=[
                Segment(start_ms=0, end_ms=1500, text="当前使用占位输出", speaker="SPEAKER_00"),
                Segment(start_ms=1500, end_ms=4300, text="待接入 FunASR AutoModel 真正推理。", speaker="SPEAKER_00"),
            ],
        )

    def _normalize_result(self, result: Any) -> TranscriptResult:
        payload = result[0] if isinstance(result, list) and result else {}
        if not isinstance(payload, dict):
            payload = {"text": str(payload)}
        text = str(payload.get("text") or "")
        language = payload.get("language")
        segments = self._extract_segments(payload, text)
        return TranscriptResult(text=text, language=str(language) if language else None, segments=segments)

    def _extract_segments(self, payload: dict[str, Any], text: str) -> list[Segment]:
        sentence_info = payload.get("sentence_info")
        if isinstance(sentence_info, list):
            segments: list[Segment] = []
            for item in sentence_info:
                if not isinstance(item, dict):
                    continue
                segment_text = str(item.get("text") or item.get("sentence") or "")
                start_ms = self._to_ms(item.get("start") or item.get("start_time") or 0)
                end_ms = self._to_ms(item.get("end") or item.get("end_time") or start_ms)
                segments.append(
                    Segment(
                        start_ms=start_ms,
                        end_ms=max(start_ms, end_ms),
                        text=segment_text,
                        speaker=item.get("speaker"),
                    )
                )
            if segments:
                return segments
        return [Segment(start_ms=0, end_ms=0, text=text, speaker="SPEAKER_00")] if text else []

    def _to_ms(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value * 1000) if value < 1000 else int(value)
        return 0
