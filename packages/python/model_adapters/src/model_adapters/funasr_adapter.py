from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np

from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters.base import ASRAdapter, AudioAsset, resolve_model_reference


class FunASRTranscribeAdapter(ASRAdapter):
    """FunASR 语音识别适配器，支持热词（hotwords）、VAD、标点、方言等高级参数。

    支持的高级特性：
    - 热词注入：提升专业术语、人名、地名等的识别准确率
    - VAD（语音活动检测）：自动过滤静音和噪声段
    - 标点预测：自动添加句号、逗号等标点符号
    - 逆文本正则化（ITN）：数字、日期、货币等格式化
    - 多语言/方言：中文（默认）、英文、粤语、四川话等
    - 时间戳输出：每个词/句的时间位置
    """

    key = "funasr-nano"
    display_name = "FunASR Nano"
    provider = "funasr"
    experimental = False

    def __init__(
        self,
        model_name: str = "FunAudioLLM/Fun-ASR-Nano-2512",
        *,
        vad_enabled: bool = False,
        vad_model: str | None = None,
        punc_enabled: bool = True,
        hotwords: list[str] | None = None,
        language: str = "zh-cn",
        itn: bool = True,
    ) -> None:
        self.model_name = resolve_model_reference(model_name)
        self._auto_model_cls: Any | None = None
        self._model: Any | None = None
        self._backend_checked = False
        # 高级参数
        self.vad_enabled = vad_enabled
        self.vad_model = vad_model or "fsmn_vad"
        self.punc_enabled = punc_enabled
        self.hotwords = hotwords or []
        self.language = language
        self.itn = itn

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
            "disable_update": True,
        }
        # VAD 配置（仅在启用时传递，避免 FunASR 尝试下载未请求的模型）
        if self.vad_enabled:
            model_kwargs["vad_model"] = self.vad_model
            model_kwargs["vad_model_revision"] = "v2.0.4"
            model_kwargs["vad_kwargs"] = {
                "chunk_size": [0, 10, 5],
                "batch_size_s": 5,
            }
        # 标点通过 itn 参数控制（FunASR-Nano 内置 ITN）
        if Path(self.model_name).exists():
            remote_code = Path(__file__).with_name("funasr_nano_remote.py")
            model_kwargs.update(
                {
                    "remote_code": remote_code.as_posix(),
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

        # 构建生成参数
        generate_kwargs: dict[str, Any] = {
            "cache": {},
            "batch_size": 1,
            "language": self.language,
            "itn": self.itn,
        }
        # 热词注入
        if self.hotwords:
            generate_kwargs["hotwords"] = self.hotwords
        # VAD 模式
        if self.vad_enabled:
            generate_kwargs["merge_vad"] = True
            generate_kwargs["merge_length_s"] = 15

        result = model.generate(input=audio_input, **generate_kwargs)
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
        # 优先从 sentence_info 提取带时间戳的分段
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
        # 从 timestamp_ns 提取词级时间戳
        timestamp = payload.get("timestamp_ns") or payload.get("timestamp")
        if isinstance(timestamp, list):
            segments = []
            for item in timestamp:
                if not isinstance(item, dict):
                    continue
                word = str(item.get("text", ""))
                start_ms = self._to_ms(item.get("start", 0))
                end_ms = self._to_ms(item.get("end", 0))
                if word:
                    segments.append(Segment(
                        start_ms=start_ms,
                        end_ms=max(start_ms, end_ms),
                        text=word,
                        speaker=None,
                    ))
            if segments:
                return segments
        return [Segment(start_ms=0, end_ms=0, text=text, speaker="SPEAKER_00")] if text else []

    def _to_ms(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            # 秒 → 毫秒（如果值 > 1000，说明已经是毫秒）
            return int(value * 1000) if value < 1000 else int(value)
        return 0
