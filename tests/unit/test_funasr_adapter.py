import torch

from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters.funasr_adapter import FunASRTranscribeAdapter


class DummyModel:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def generate(self, input, **kwargs):
        chunk_len = int(input.shape[0])
        self.calls.append(chunk_len)
        text = f"片段{len(self.calls)}"
        return [{
            "text": text,
            "sentence_info": [
                {
                    "text": text,
                    "start": 0,
                    "end": 1000,
                }
            ],
        }]


class DummyVadModel:
    def __init__(self, segments):
        self.segments = segments

    def generate(self, input, **kwargs):
        return [{"value": self.segments}]


def test_build_audio_chunks_splits_long_waveform() -> None:
    adapter = FunASRTranscribeAdapter()
    adapter.chunk_seconds = 2.0
    adapter.chunk_overlap_seconds = 0.5

    audio = torch.zeros(5 * 16000, dtype=torch.float32)
    chunks = adapter._build_audio_chunks(audio, 16000)

    assert len(chunks) == 3
    assert chunks[0][1] == 0
    assert chunks[1][1] == 1500
    assert chunks[2][1] == 3000


def test_transcribe_chunked_offsets_segments_and_merges_text() -> None:
    adapter = FunASRTranscribeAdapter()
    adapter.chunk_seconds = 2.0
    adapter.chunk_overlap_seconds = 0.0
    model = DummyModel()
    audio = torch.zeros(5 * 16000, dtype=torch.float32)

    result = adapter._transcribe_chunked(
        model,
        audio,
        16000,
        {"cache": {}, "batch_size": 1, "language": "zh-cn", "itn": True},
    )

    assert isinstance(result, TranscriptResult)
    assert result.text == "片段1片段2片段3"
    assert [segment.start_ms for segment in result.segments] == [0, 2000, 4000]
    assert [segment.end_ms for segment in result.segments] == [1000, 3000, 5000]
    assert len(model.calls) == 3


def test_merge_chunk_texts_inserts_space_for_ascii_words() -> None:
    adapter = FunASRTranscribeAdapter()

    merged = adapter._merge_chunk_texts(["hello", "world", "中文", "继续"])

    assert merged == "hello world中文继续"


def test_merge_chunk_texts_removes_overlap_from_adjacent_chunks() -> None:
    adapter = FunASRTranscribeAdapter()

    merged = adapter._merge_chunk_texts(["平台功能已经通了", "已经通了，没什么问题"])

    assert merged == "平台功能已经通了，没什么问题"


def test_ensure_timed_segments_backfills_sentence_timestamps_when_model_does_not_return_them() -> None:
    adapter = FunASRTranscribeAdapter()
    transcript = TranscriptResult(
        text="第一句。第二句！第三句？",
        language="zh-cn",
        segments=[Segment(start_ms=0, end_ms=0, text="第一句。第二句！第三句？", speaker=None)],
    )

    normalized = adapter._ensure_timed_segments(transcript, 9000)

    assert len(normalized.segments) == 3
    assert normalized.segments[0].start_ms == 0
    assert normalized.segments[-1].end_ms == 9000
    assert normalized.segments[1].text == "第二句！"


def test_normalize_transcript_text_removes_repeated_phrases_and_cjk_spaces() -> None:
    adapter = FunASRTranscribeAdapter()

    normalized = adapter._normalize_transcript_text("做到的 对吧？ 做到的 对吧？ 文 文档 平台")

    assert normalized == "做到的对吧？ 文文档平台"


def test_normalize_transcript_text_dedupes_short_repeated_tokens() -> None:
    adapter = FunASRTranscribeAdapter()

    normalized = adapter._normalize_transcript_text("可以去 可以去 尝试一下 对对对对")

    assert "可以去 可以去" not in normalized
    assert "对对对对" not in normalized


def test_normalize_transcript_text_collapses_common_cjk_stutter_runs() -> None:
    adapter = FunASRTranscribeAdapter()

    normalized = adapter._normalize_transcript_text(
        "呃这这种方案 主主业务流程 我我其实 有有什么看法 最最严重的账号密码 层层面去看 就就在提"
    )

    assert "这这种" not in normalized
    assert "主主业务" not in normalized
    assert "我我其实" not in normalized
    assert "有有什么" not in normalized
    assert "最最严重" not in normalized
    assert "层层面" not in normalized
    assert "就就在" not in normalized
    assert "这种方案" in normalized
    assert "主业务流程" in normalized
    assert "我其实" in normalized
    assert "有什么看法" in normalized
    assert "最严重的账号密码" in normalized
    assert "层面去看" in normalized
    assert "就在提" in normalized


def test_normalize_transcript_text_preserves_common_valid_reduplication_words() -> None:
    adapter = FunASRTranscribeAdapter()

    normalized = adapter._normalize_transcript_text("刚刚开始 常常这样 人人都知道 天天都会发生")

    assert "刚刚开始" in normalized
    assert "常常这样" in normalized
    assert "人人都知道" in normalized
    assert "天天都会发生" in normalized


def test_funasr_adapter_defaults_vad_model_to_local_models_directory() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)

    assert "FSMN-VAD" in adapter.vad_model


def test_build_generate_kwargs_limits_vad_segment_time_by_chunk_duration() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.vad_max_single_segment_ms = 30000

    kwargs = adapter._build_generate_kwargs(12000)

    assert kwargs["batch_size"] == 1
    assert kwargs["vad_kwargs"]["max_single_segment_time"] == 12000


def test_extract_segments_merges_close_sentence_info_fragments() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    payload = {
        "sentence_info": [
            {"text": "这是第", "start": 0, "end": 1500},
            {"text": "一句。", "start": 1700, "end": 2100},
            {"text": "第二句。", "start": 3200, "end": 4000},
        ]
    }

    segments = adapter._extract_segments(payload, "这是第一句。第二句。")

    assert len(segments) == 2
    assert segments[0].text == "这是第一句。"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 2100


def test_merge_close_vad_segments_merges_small_gap_and_preserves_large_gap() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.vad_merge_gap_ms = 400

    merged = adapter._merge_close_vad_segments([(0, 1200), (1450, 2200), (3200, 3800)])

    assert merged == [(0, 2200), (3200, 3800)]


def test_build_vad_subsegments_adds_padding_and_splits_long_segment() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.vad_segment_padding_ms = 150
    adapter.vad_max_single_segment_ms = 3000
    adapter.vad_subsegment_overlap_ms = 250

    subsegments = adapter._build_vad_subsegments([(1000, 5200)], 6000)

    assert subsegments[0]["slice_start_ms"] == 850
    assert subsegments[0]["speech_start_ms"] == 1000
    assert subsegments[-1]["speech_end_ms"] == 5200
    assert len(subsegments) >= 2


def test_merge_short_vad_segments_absorbs_tiny_middle_segment() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.min_vad_speech_segment_ms = 1200

    merged = adapter._merge_short_vad_segments([(0, 1800), (2200, 2600), (2800, 4500)])

    assert merged == [(0, 1800), (2200, 4500)]


def test_coalesce_short_subsegments_reduces_fragmented_calls() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.min_vad_speech_segment_ms = 1200
    segments = [
        {"slice_start_ms": 0, "slice_end_ms": 1600, "speech_start_ms": 100, "speech_end_ms": 1200},
        {"slice_start_ms": 1700, "slice_end_ms": 2200, "speech_start_ms": 1800, "speech_end_ms": 2100},
        {"slice_start_ms": 2250, "slice_end_ms": 3900, "speech_start_ms": 2300, "speech_end_ms": 3600},
    ]

    merged = adapter._coalesce_short_subsegments(segments)

    assert len(merged) == 2
    assert merged[0]["slice_end_ms"] == 2200
    assert merged[1]["slice_start_ms"] == 2250


def test_segment_chunk_with_vad_uses_vad_boundaries_when_available() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter._load_vad_runtime_model = lambda: DummyVadModel([[1500, 1800], [2350, 2600]])
    audio = torch.zeros(4 * 16000, dtype=torch.float32)

    segments = adapter._segment_chunk_with_vad(audio, 16000)

    assert len(segments) == 1
    assert segments[0]["speech_start_ms"] == 1500
    assert segments[0]["speech_end_ms"] == 2600


def test_transcribe_chunked_uses_vad_subsegments_for_offsets() -> None:
    adapter = FunASRTranscribeAdapter(vad_enabled=True)
    adapter.chunk_seconds = 5.0
    adapter.chunk_overlap_seconds = 0.0
    adapter._segment_chunk_with_vad = lambda chunk_audio, sample_rate: [
        {
            "slice_start_ms": 0,
            "slice_end_ms": 1500,
            "speech_start_ms": 0,
            "speech_end_ms": 1500,
        },
        {
            "slice_start_ms": 2000,
            "slice_end_ms": 3500,
            "speech_start_ms": 2000,
            "speech_end_ms": 3500,
        },
    ]
    model = DummyModel()
    audio = torch.zeros(5 * 16000, dtype=torch.float32)

    result = adapter._transcribe_chunked(
        model,
        audio,
        16000,
        {"cache": {}, "batch_size": 1, "language": "zh-cn", "itn": True},
    )

    assert result.text == "片段1片段2"
    assert [segment.start_ms for segment in result.segments] == [0, 2000]
    assert [segment.end_ms for segment in result.segments] == [1000, 3000]
