from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import numpy as np

from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters.base import (
    ASRAdapter,
    AudioAsset,
    has_cuda_runtime,
    require_available_model,
    resolve_model_reference,
)


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
        model_name: str = "models/Fun-ASR-Nano-2512",
        *,
        vad_enabled: bool = False,
        vad_model: str | None = None,
        punc_enabled: bool = True,
        hotwords: list[str] | None = None,
        language: str = "zh-cn",
        itn: bool = True,
    ) -> None:
        self.model_name = resolve_model_reference(model_name)
        self.vad_model = resolve_model_reference(vad_model or "models/FSMN-VAD")
        self._auto_model_cls: Any | None = None
        self._model: Any | None = None
        self._vad_runtime_model: Any | None = None
        self._backend_checked = False
        # 高级参数
        self.vad_enabled = vad_enabled
        self.punc_enabled = punc_enabled
        self.hotwords = hotwords or []
        self.language = language
        self.itn = itn
        self.max_single_pass_seconds = 45.0
        self.chunk_seconds = 20.0
        self.chunk_overlap_seconds = 1.5
        self.vad_max_single_segment_ms = 30000
        self.vad_merge_gap_ms = 400
        self.vad_segment_padding_ms = 150
        self.vad_subsegment_overlap_ms = 250
        self.min_vad_speech_segment_ms = 1200
        self.short_sentence_merge_gap_ms = 800
        self.short_sentence_merge_duration_ms = 1200

    @property
    def availability(self) -> str:
        has_local_model = _has_model_artifacts(self.model_name)
        if not has_local_model:
            return "unavailable"
        return "available" if self._ensure_backend() and has_cuda_runtime() else "unavailable"

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
        if not has_cuda_runtime():
            raise RuntimeError("FunASR 高精度推理要求 CUDA GPU 可用，当前运行时未检测到可用 CUDA。")
        return "cuda:0"

    def _load_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        if not _has_model_artifacts(self.model_name):
            return None
        if not self._ensure_backend():
            return None
        model_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "trust_remote_code": True,
            "device": self._resolve_device(),
            "disable_update": True,
        }
        # VAD 配置（仅在启用时传递，避免 FunASR 尝试下载未请求的模型）
        if self.vad_enabled and _has_model_artifacts(self.vad_model):
            model_kwargs["vad_model"] = self.vad_model
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

    def _load_vad_runtime_model(self) -> Any | None:
        if self._vad_runtime_model is not None:
            return self._vad_runtime_model
        if not self.vad_enabled or not _has_model_artifacts(self.vad_model):
            return None
        if not self._ensure_backend():
            return None
        self._vad_runtime_model = self._auto_model_cls(
            model=self.vad_model,
            device=self._resolve_device(),
            disable_update=True,
        )
        return self._vad_runtime_model

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
        require_available_model(self.availability, model_label=self.display_name, purpose="语音转写")
        model = self._load_model()
        if model is None:
            raise RuntimeError(f"{self.display_name} 未能成功加载本地 CUDA 推理模型。")
        audio_input = self._load_audio_input(asset)
        import torch

        duration_seconds = self._estimate_duration_seconds(audio_input, asset.sample_rate)
        generate_kwargs = self._build_generate_kwargs(
            None if duration_seconds is None else int(duration_seconds * 1000)
        )
        if duration_seconds is not None and duration_seconds > self.max_single_pass_seconds:
            return self._transcribe_chunked(model, audio_input, asset.sample_rate, generate_kwargs)

        try:
            result = model.generate(input=audio_input, **generate_kwargs)
            _clear_cuda_cache()
            normalized = self._normalize_result(result)
            if duration_seconds is not None:
                normalized = self._ensure_timed_segments(normalized, int(duration_seconds * 1000))
            return normalized
        except torch.OutOfMemoryError:
            if duration_seconds is None:
                raise
            torch.cuda.empty_cache()
            return self._transcribe_chunked(model, audio_input, asset.sample_rate, generate_kwargs)

    def _estimate_duration_seconds(self, audio_input: Any, sample_rate: int) -> float | None:
        if hasattr(audio_input, "shape") and len(audio_input.shape) >= 1:
            return float(audio_input.shape[0]) / float(max(sample_rate, 1))
        if isinstance(audio_input, np.ndarray):
            return float(audio_input.shape[0]) / float(max(sample_rate, 1))
        return None

    def _transcribe_chunked(
        self,
        model: Any,
        audio_input: Any,
        sample_rate: int,
        generate_kwargs: dict[str, Any],
    ) -> TranscriptResult:
        import torch

        chunks = self._build_audio_chunks(audio_input, sample_rate)
        if len(chunks) <= 1 and not self.vad_enabled:
            result = model.generate(input=audio_input, **generate_kwargs)
            _clear_cuda_cache()
            return self._normalize_result(result)

        merged_text_parts: list[str] = []
        merged_segments: list[Segment] = []
        merged_language: str | None = None

        for index, (chunk_audio, offset_ms, _) in enumerate(chunks):
            chunk_duration_s = self._estimate_duration_seconds(chunk_audio, sample_rate)
            chunk_duration_ms = None if chunk_duration_s is None else int(chunk_duration_s * 1000)
            trim_before_ms = None if index == 0 else offset_ms + int(self.chunk_overlap_seconds * 1000)
            chunk_ranges = self._segment_chunk_with_vad(chunk_audio, sample_rate)
            for sub_index, (segment_audio, segment_offset_ms, logical_start_ms) in enumerate(
                self._iter_chunk_subsegments(chunk_audio, chunk_ranges, sample_rate)
            ):
                sub_duration_s = self._estimate_duration_seconds(segment_audio, sample_rate)
                sub_duration_ms = None if sub_duration_s is None else int(sub_duration_s * 1000)
                chunk_generate_kwargs = self._build_generate_kwargs(sub_duration_ms)
                result = model.generate(input=segment_audio, **chunk_generate_kwargs)
                normalized = self._normalize_result(result)
                if sub_duration_ms is not None:
                    normalized = self._ensure_timed_segments(normalized, sub_duration_ms)
                if normalized.text:
                    merged_text_parts.append(
                        normalized.text
                        if not merged_text_parts
                        else self._trim_chunk_prefix_text(merged_text_parts[-1], normalized.text)
                    )
                if merged_language is None and normalized.language:
                    merged_language = normalized.language
                sub_trim_before_ms = trim_before_ms
                absolute_logical_start_ms = offset_ms + logical_start_ms
                if sub_index > 0:
                    sub_trim_before_ms = max(
                        absolute_logical_start_ms,
                        trim_before_ms or absolute_logical_start_ms,
                    )
                self._append_chunk_segments(
                    merged_segments,
                    normalized.segments,
                    offset_ms + segment_offset_ms,
                    sub_trim_before_ms,
                )
                _clear_cuda_cache()

            if not chunk_ranges and chunk_duration_ms is not None:
                normalized = self._ensure_timed_segments(TranscriptResult(text="", language=merged_language, segments=[]), chunk_duration_ms)
                self._append_chunk_segments(merged_segments, normalized.segments, offset_ms, trim_before_ms)

        merged_text = self._merge_chunk_texts(merged_text_parts)
        if not merged_segments and merged_text:
            merged_segments = [Segment(start_ms=0, end_ms=0, text=merged_text, speaker=None)]
        return TranscriptResult(text=merged_text, language=merged_language, segments=merged_segments)

    def _segment_chunk_with_vad(self, chunk_audio: Any, sample_rate: int) -> list[dict[str, int]]:
        duration_ms = self._audio_duration_ms(chunk_audio, sample_rate)
        if duration_ms <= 0:
            return []
        default_segment = [{
            "slice_start_ms": 0,
            "slice_end_ms": duration_ms,
            "speech_start_ms": 0,
            "speech_end_ms": duration_ms,
        }]
        if not self.vad_enabled:
            return default_segment
        vad_model = self._load_vad_runtime_model()
        if vad_model is None:
            return default_segment

        try:
            result = vad_model.generate(input=self._prepare_vad_input(chunk_audio))
        except Exception:
            return default_segment
        segments = self._parse_vad_segments(result)
        if not segments:
            return default_segment
        merged_segments = self._merge_close_vad_segments(segments)
        merged_segments = self._merge_short_vad_segments(merged_segments)
        bounded = self._build_vad_subsegments(merged_segments, duration_ms)
        return bounded or default_segment

    def _iter_chunk_subsegments(
        self,
        chunk_audio: Any,
        chunk_ranges: list[dict[str, int]],
        sample_rate: int,
    ) -> list[tuple[Any, int, int]]:
        if not hasattr(chunk_audio, "__getitem__"):
            return [(chunk_audio, 0, 0)]
        segments: list[tuple[Any, int, int]] = []
        for item in chunk_ranges:
            slice_start_ms = int(item["slice_start_ms"])
            slice_end_ms = int(item["slice_end_ms"])
            logical_start_ms = int(item["speech_start_ms"])
            start_sample = max(0, int(slice_start_ms * sample_rate / 1000))
            end_sample = max(start_sample + 1, int(slice_end_ms * sample_rate / 1000))
            segments.append((chunk_audio[start_sample:end_sample], slice_start_ms, logical_start_ms))
        return segments

    def _audio_duration_ms(self, audio_input: Any, sample_rate: int) -> int:
        duration_seconds = self._estimate_duration_seconds(audio_input, sample_rate)
        return 0 if duration_seconds is None else int(duration_seconds * 1000)

    def _prepare_vad_input(self, chunk_audio: Any) -> Any:
        if hasattr(chunk_audio, "detach"):
            return chunk_audio.detach().cpu().numpy().astype(np.float32).tolist()
        if isinstance(chunk_audio, np.ndarray):
            return chunk_audio.astype(np.float32).tolist()
        return chunk_audio

    def _parse_vad_segments(self, result: Any) -> list[tuple[int, int]]:
        payload = result[0] if isinstance(result, list) and result else result
        if not isinstance(payload, dict):
            return []
        raw_segments = payload.get("value") or payload.get("segments") or []
        parsed: list[tuple[int, int]] = []
        for item in raw_segments:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            start_ms = self._to_ms(item[0])
            end_ms = self._to_ms(item[1])
            if end_ms > start_ms:
                parsed.append((start_ms, end_ms))
        return parsed

    def _merge_close_vad_segments(self, segments: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not segments:
            return []
        merged: list[tuple[int, int]] = [segments[0]]
        for start_ms, end_ms in segments[1:]:
            previous_start, previous_end = merged[-1]
            if 0 <= start_ms - previous_end <= self.vad_merge_gap_ms:
                merged[-1] = (previous_start, max(previous_end, end_ms))
                continue
            merged.append((start_ms, end_ms))
        return merged

    def _build_vad_subsegments(
        self,
        segments: list[tuple[int, int]],
        duration_ms: int,
    ) -> list[dict[str, int]]:
        built: list[dict[str, int]] = []
        for start_ms, end_ms in segments:
            speech_start_ms = max(0, start_ms)
            speech_end_ms = min(duration_ms, end_ms)
            slice_start_ms = max(0, speech_start_ms - self.vad_segment_padding_ms)
            slice_end_ms = min(duration_ms, speech_end_ms + self.vad_segment_padding_ms)
            built.extend(
                self._split_long_vad_subsegments(
                    slice_start_ms,
                    slice_end_ms,
                    speech_start_ms,
                    speech_end_ms,
                    duration_ms,
                )
            )
        return self._coalesce_short_subsegments(built)

    def _merge_short_vad_segments(self, segments: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if len(segments) <= 1:
            return segments
        merged = [list(item) for item in segments]
        index = 0
        while index < len(merged):
            start_ms, end_ms = merged[index]
            duration_ms = end_ms - start_ms
            if duration_ms >= self.min_vad_speech_segment_ms:
                index += 1
                continue
            previous = merged[index - 1] if index > 0 else None
            following = merged[index + 1] if index + 1 < len(merged) else None
            prev_gap = None if previous is None else max(0, start_ms - previous[1])
            next_gap = None if following is None else max(0, following[0] - end_ms)
            can_merge_prev = previous is not None and prev_gap <= max(self.vad_merge_gap_ms * 2, 900)
            can_merge_next = following is not None and next_gap <= max(self.vad_merge_gap_ms * 2, 900)
            if not can_merge_prev and not can_merge_next:
                index += 1
                continue
            if can_merge_prev and (not can_merge_next or (prev_gap or 0) <= (next_gap or 0)):
                previous[1] = max(previous[1], end_ms)
                merged.pop(index)
                continue
            if can_merge_next:
                following[0] = min(following[0], start_ms)
                merged.pop(index)
                continue
            index += 1
        return [(int(start_ms), int(end_ms)) for start_ms, end_ms in merged]

    def _split_long_vad_subsegments(
        self,
        slice_start_ms: int,
        slice_end_ms: int,
        speech_start_ms: int,
        speech_end_ms: int,
        duration_ms: int,
    ) -> list[dict[str, int]]:
        max_span_ms = max(1000, int(self.vad_max_single_segment_ms))
        if slice_end_ms - slice_start_ms <= max_span_ms:
            return [{
                "slice_start_ms": slice_start_ms,
                "slice_end_ms": slice_end_ms,
                "speech_start_ms": speech_start_ms,
                "speech_end_ms": speech_end_ms,
            }]

        step_ms = max(1000, max_span_ms - self.vad_subsegment_overlap_ms)
        result: list[dict[str, int]] = []
        cursor = slice_start_ms
        while cursor < slice_end_ms:
            end_ms = min(slice_end_ms, cursor + max_span_ms)
            result.append(
                {
                    "slice_start_ms": cursor,
                    "slice_end_ms": end_ms,
                    "speech_start_ms": max(speech_start_ms, cursor),
                    "speech_end_ms": min(speech_end_ms, end_ms),
                }
            )
            if end_ms >= slice_end_ms:
                break
            cursor += step_ms
        if result:
            result[-1]["slice_end_ms"] = min(duration_ms, result[-1]["slice_end_ms"])
            result[-1]["speech_end_ms"] = min(duration_ms, result[-1]["speech_end_ms"])
        return result

    def _coalesce_short_subsegments(self, segments: list[dict[str, int]]) -> list[dict[str, int]]:
        if len(segments) <= 1:
            return segments
        merged = [dict(item) for item in segments]
        index = 0
        while index < len(merged):
            current = merged[index]
            speech_duration_ms = int(current["speech_end_ms"]) - int(current["speech_start_ms"])
            if speech_duration_ms >= self.min_vad_speech_segment_ms:
                index += 1
                continue
            previous = merged[index - 1] if index > 0 else None
            following = merged[index + 1] if index + 1 < len(merged) else None
            if previous is None and following is None:
                index += 1
                continue
            if previous is not None and (
                following is None
                or int(current["slice_start_ms"]) - int(previous["slice_end_ms"])
                <= int(following["slice_start_ms"]) - int(current["slice_end_ms"])
            ):
                previous["slice_end_ms"] = max(int(previous["slice_end_ms"]), int(current["slice_end_ms"]))
                previous["speech_end_ms"] = max(int(previous["speech_end_ms"]), int(current["speech_end_ms"]))
                merged.pop(index)
                continue
            if following is not None:
                following["slice_start_ms"] = min(int(following["slice_start_ms"]), int(current["slice_start_ms"]))
                following["speech_start_ms"] = min(int(following["speech_start_ms"]), int(current["speech_start_ms"]))
                merged.pop(index)
                continue
            index += 1
        return merged

    def _build_generate_kwargs(self, chunk_duration_ms: int | None) -> dict[str, Any]:
        generate_kwargs: dict[str, Any] = {
            "cache": {},
            "batch_size": 1,
            "language": self.language,
            "itn": self.itn,
        }
        if self.hotwords:
            generate_kwargs["hotwords"] = self.hotwords
        if self.vad_enabled:
            generate_kwargs["merge_vad"] = True
            generate_kwargs["merge_length_s"] = 15
            max_single_segment_time = self.vad_max_single_segment_ms
            if chunk_duration_ms is not None:
                max_single_segment_time = min(max_single_segment_time, max(1000, chunk_duration_ms))
            generate_kwargs["vad_kwargs"] = {
                "max_single_segment_time": max_single_segment_time,
            }
        return generate_kwargs

    def _build_audio_chunks(self, audio_input: Any, sample_rate: int) -> list[tuple[Any, int, int]]:
        if not hasattr(audio_input, "shape") or len(audio_input.shape) < 1:
            return [(audio_input, 0, 0)]

        total_samples = int(audio_input.shape[0])
        chunk_samples = int(self.chunk_seconds * sample_rate)
        overlap_samples = int(self.chunk_overlap_seconds * sample_rate)
        step_samples = max(1, chunk_samples - overlap_samples)
        if chunk_samples <= 0 or total_samples <= chunk_samples:
            return [(audio_input, 0, int(total_samples * 1000 / sample_rate))]

        chunks: list[tuple[Any, int, int]] = []
        for start in range(0, total_samples, step_samples):
            end = min(start + chunk_samples, total_samples)
            if end <= start:
                continue
            chunks.append(
                (
                    audio_input[start:end],
                    int(start * 1000 / sample_rate),
                    int(end * 1000 / sample_rate),
                )
            )
            if end >= total_samples:
                break
        return chunks

    def _merge_chunk_texts(self, texts: list[str]) -> str:
        merged = ""
        for item in texts:
            clean = self._normalize_transcript_text(item)
            if not clean:
                continue
            if not merged:
                merged = clean
                continue
            overlap = self._find_text_overlap(merged, clean)
            remainder = clean[overlap:]
            if not remainder:
                continue
            if self._needs_space_between(merged[-1], remainder[0]):
                merged = f"{merged} {remainder}"
            else:
                merged = f"{merged}{remainder}"
        return merged

    def _trim_chunk_prefix_text(self, previous_text: str, current_text: str) -> str:
        overlap = self._find_text_overlap(previous_text, current_text)
        trimmed = current_text[overlap:] if overlap else current_text
        return self._normalize_transcript_text(trimmed)

    def _find_text_overlap(self, left: str, right: str, *, min_overlap: int = 4, max_window: int = 80) -> int:
        left_clean = (left or "").strip()
        right_clean = (right or "").strip()
        max_len = min(len(left_clean), len(right_clean), max_window)
        for size in range(max_len, min_overlap - 1, -1):
            if left_clean[-size:] == right_clean[:size]:
                return size
        return 0

    def _append_chunk_segments(
        self,
        merged_segments: list[Segment],
        chunk_segments: list[Segment],
        offset_ms: int,
        trim_before_ms: int | None,
    ) -> None:
        for segment in chunk_segments:
            start_ms = segment.start_ms + offset_ms
            end_ms = segment.end_ms + offset_ms
            if trim_before_ms is not None and end_ms <= trim_before_ms:
                continue
            text = segment.text
            if trim_before_ms is not None and start_ms < trim_before_ms:
                start_ms = trim_before_ms
            text = self._normalize_transcript_text(text)
            if merged_segments:
                previous = merged_segments[-1]
                if start_ms < previous.end_ms:
                    start_ms = previous.end_ms
                if text and previous.text:
                    overlap = self._find_text_overlap(previous.text, text, min_overlap=3, max_window=32)
                    if overlap:
                        text = text[overlap:]
            if end_ms <= start_ms:
                continue
            merged_segments.append(
                Segment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=self._normalize_transcript_text(text),
                    speaker=segment.speaker,
                    confidence=segment.confidence,
                )
            )

    def _ensure_timed_segments(self, transcript: TranscriptResult, duration_ms: int) -> TranscriptResult:
        if duration_ms <= 0:
            return transcript
        if transcript.segments and any(segment.end_ms > segment.start_ms for segment in transcript.segments):
            return transcript

        sentences = self._split_text_for_timestamps(transcript.text)
        if not sentences:
            return TranscriptResult(
                text=transcript.text,
                language=transcript.language,
                segments=[Segment(start_ms=0, end_ms=duration_ms, text=transcript.text, speaker=None)] if transcript.text else [],
            )

        total_chars = max(1, sum(len(item) for item in sentences))
        built_segments: list[Segment] = []
        cursor = 0
        for index, sentence in enumerate(sentences):
            start_ms = cursor
            if index == len(sentences) - 1:
                end_ms = duration_ms
            else:
                share = max(1, round(duration_ms * len(sentence) / total_chars))
                end_ms = min(duration_ms, start_ms + share)
            built_segments.append(
                Segment(
                    start_ms=start_ms,
                    end_ms=max(start_ms + 1, end_ms),
                    text=sentence,
                    speaker=None,
                )
            )
            cursor = built_segments[-1].end_ms

        if built_segments:
            built_segments[-1] = built_segments[-1].model_copy(update={"end_ms": duration_ms})
        return TranscriptResult(
            text=self._normalize_transcript_text(transcript.text),
            language=transcript.language,
            segments=[
                segment.model_copy(update={"text": self._normalize_transcript_text(segment.text)})
                for segment in built_segments
            ],
        )

    def _split_text_for_timestamps(self, text: str) -> list[str]:
        content = (text or "").strip()
        if not content:
            return []
        raw_parts = re.split(r"(?<=[。！？!?；;])", content)
        parts = [part.strip() for part in raw_parts if part and part.strip()]
        if parts:
            return parts
        return [content]

    def _needs_space_between(self, left: str, right: str) -> bool:
        ascii_word = re.compile(r"[A-Za-z0-9]")
        return bool(ascii_word.match(left) and ascii_word.match(right))

    def _normalize_result(self, result: Any) -> TranscriptResult:
        payload = result[0] if isinstance(result, list) and result else {}
        if not isinstance(payload, dict):
            payload = {"text": str(payload)}
        text = self._normalize_transcript_text(str(payload.get("text") or ""))
        language = payload.get("language")
        segments = self._extract_segments(payload, text)
        segments = [
            segment.model_copy(update={"text": self._normalize_transcript_text(segment.text)})
            for segment in segments
        ]
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
                        text=self._normalize_transcript_text(segment_text),
                        speaker=item.get("speaker"),
                    )
                )
            if segments:
                return self._consolidate_sentence_segments(segments)
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
                        text=self._normalize_transcript_text(word),
                        speaker=None,
                    ))
            if segments:
                return segments
        return [Segment(start_ms=0, end_ms=0, text=self._normalize_transcript_text(text), speaker=None)] if text else []

    def _to_ms(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            # 秒 → 毫秒（如果值 > 1000，说明已经是毫秒）
            return int(value * 1000) if value < 1000 else int(value)
        return 0

    def _normalize_transcript_text(self, text: str | None) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)
        cleaned = re.sub(r"\s+([，。！？；：、“”‘’,.!?;:])", r"\1", cleaned)
        cleaned = re.sub(r"([，。！？；,.!?;])\1+", r"\1", cleaned)
        cleaned = self._collapse_cjk_stutter_runs(cleaned)
        cleaned = self._dedupe_adjacent_phrase(cleaned)
        cleaned = self._dedupe_repeated_prefix_clause(cleaned)
        cleaned = self._dedupe_repeated_tokens(cleaned)
        return cleaned.strip()

    def _merge_close_sentence_segments(self, segments: list[Segment]) -> list[Segment]:
        if not segments:
            return []
        merged: list[Segment] = [segments[0]]
        for segment in segments[1:]:
            previous = merged[-1]
            same_speaker = previous.speaker == segment.speaker
            close_gap = 0 <= segment.start_ms - previous.end_ms <= self.vad_merge_gap_ms
            if same_speaker and close_gap:
                joined_text = self._join_sentence_text(previous.text, segment.text)
                merged[-1] = previous.model_copy(
                    update={
                        "end_ms": max(previous.end_ms, segment.end_ms),
                        "text": joined_text,
                    }
                )
                continue
            merged.append(segment)
        return merged

    def _consolidate_sentence_segments(self, segments: list[Segment]) -> list[Segment]:
        merged = self._merge_close_sentence_segments(segments)
        if len(merged) <= 1:
            return merged

        compacted: list[Segment] = [merged[0]]
        for segment in merged[1:]:
            previous = compacted[-1]
            gap_ms = segment.start_ms - previous.end_ms
            if (
                previous.speaker == segment.speaker
                and 0 <= gap_ms <= self.short_sentence_merge_gap_ms
                and self._should_merge_sentence_followup(previous, segment)
            ):
                compacted[-1] = previous.model_copy(
                    update={
                        "end_ms": max(previous.end_ms, segment.end_ms),
                        "text": self._join_sentence_text(previous.text, segment.text),
                    }
                )
                continue
            compacted.append(segment)
        return compacted

    def _should_merge_sentence_followup(self, previous: Segment, current: Segment) -> bool:
        previous_text = self._normalize_transcript_text(previous.text)
        current_text = self._normalize_transcript_text(current.text)
        if not previous_text or not current_text:
            return False
        if self._is_short_sentence_followup(current_text):
            return True
        if self._is_incomplete_sentence(previous_text):
            return True
        if (previous.end_ms - previous.start_ms) <= self.short_sentence_merge_duration_ms:
            return True
        overlap = self._find_text_overlap(previous_text, current_text, min_overlap=3, max_window=24)
        return overlap >= 3

    def _join_sentence_text(self, left: str, right: str) -> str:
        left_clean = self._normalize_transcript_text(left)
        right_clean = self._normalize_transcript_text(right)
        if not left_clean:
            return right_clean
        if not right_clean:
            return left_clean
        overlap = self._find_text_overlap(left_clean, right_clean, min_overlap=3, max_window=32)
        if overlap:
            right_clean = right_clean[overlap:]
        if not right_clean:
            return left_clean
        return self._normalize_transcript_text(f"{left_clean}{right_clean}")

    def _is_incomplete_sentence(self, text: str) -> bool:
        normalized = self._normalize_transcript_text(text)
        if not normalized:
            return False
        return not re.search(r"[。！？!?；;]$", normalized)

    def _is_short_sentence_followup(self, text: str) -> bool:
        normalized = self._normalize_transcript_text(text)
        if not normalized:
            return False
        if len(normalized) <= 4 and not re.search(r"[。！？!?；;]$", normalized):
            return True
        fillers = {
            "啊",
            "嗯",
            "呃",
            "额",
            "哦",
            "哎",
            "对吧",
            "是吧",
            "然后",
            "就是",
        }
        stripped = re.sub(r"[，。！？；,.!?;\s]", "", normalized)
        return stripped in fillers

    def _dedupe_adjacent_phrase(self, text: str) -> str:
        cleaned = text
        for size in range(2, 13):
            pattern = re.compile(rf"(.{{{size}}})(?:\s*[，。！？；,.!?;]?\s*)\1+")
            while True:
                updated = pattern.sub(r"\1", cleaned)
                if updated == cleaned:
                    break
                cleaned = updated
        return cleaned

    def _dedupe_repeated_tokens(self, text: str) -> str:
        parts = [item for item in re.split(r"(\s+)", text) if item]
        result: list[str] = []
        previous_normalized = ""
        repeat_count = 0
        for part in parts:
            if part.isspace():
                if result and not result[-1].isspace():
                    result.append(" ")
                continue
            normalized = re.sub(r"[，。！？；：、“”‘’,.!?;:\-\s]", "", part)
            if normalized and normalized == previous_normalized and len(normalized) <= 6:
                repeat_count += 1
                if repeat_count >= 1:
                    continue
            else:
                repeat_count = 0
            result.append(part)
            if normalized:
                previous_normalized = normalized
        return "".join(result)

    def _dedupe_repeated_prefix_clause(self, text: str) -> str:
        cleaned = text
        patterns = [
            re.compile(r"([\u4e00-\u9fff]{2,3})[\u4e00-\u9fff]{0,2}\1(?=[\u4e00-\u9fff])"),
            re.compile(r"([\u4e00-\u9fff]{2,4})(?:\s*[，。！？；,.!?;]?\s*)\1(?=[\u4e00-\u9fff])"),
        ]
        for pattern in patterns:
            while True:
                updated = pattern.sub(r"\1", cleaned)
                if updated == cleaned:
                    break
                cleaned = updated
        for pattern, replacement in (
            (re.compile(r"通过[^，。！？；]{0,2}通过"), "通过"),
            (re.compile(r"按照[^，。！？；]{0,2}按照"), "按照"),
        ):
            updated = pattern.sub(replacement, cleaned)
            if updated != cleaned:
                cleaned = updated
        return cleaned

    def _collapse_cjk_stutter_runs(self, text: str) -> str:
        cleaned = text
        # 只处理会议口语里高频、低风险的口吃前缀字，避免误伤“刚刚开始”“文文档”这类合法词形。
        cleaned = re.sub(
            r"([这那有就我你他她它主最层好])[ \t]*\1+(?=[\u4e00-\u9fff])",
            r"\1",
            cleaned,
        )
        return cleaned


def _has_model_artifacts(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.exists():
        return False
    if candidate.is_file():
        return candidate.name != ".gitkeep"
    return any(item.is_file() and item.name != ".gitkeep" for item in candidate.rglob("*"))


def _clear_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        return
