from apps.worker.app.pipelines.alignment import (
    align_transcript_with_speakers,
    build_display_speaker_timeline,
    build_exclusive_speaker_timeline,
    merge_short_segments,
)
from domain.schemas.transcript import Segment, TranscriptResult


def test_align_transcript_splits_segment_by_diarization_timeline() -> None:
    transcript = TranscriptResult(
        text="甲方先说，乙方再说。",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=4000, text="甲方先说，乙方再说。", speaker=None, confidence=0.9),
        ],
    )
    diarization_segments = [
        Segment(start_ms=0, end_ms=1500, text="", speaker="SPEAKER_00", confidence=0.95),
        Segment(start_ms=1500, end_ms=4000, text="", speaker="SPEAKER_01", confidence=0.95),
    ]

    result = align_transcript_with_speakers(transcript, diarization_segments)

    assert len(result.segments) == 2
    assert result.segments[0].speaker == "SPEAKER_00"
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 1500
    assert result.segments[1].speaker == "SPEAKER_01"
    assert result.segments[1].start_ms == 1500
    assert result.segments[1].end_ms == 4000
    assert "甲方" in result.segments[0].text
    assert "乙方" in result.segments[1].text


def test_align_transcript_smooths_tiny_alternating_speaker_fragments() -> None:
    transcript = TranscriptResult(
        text="第一句。第二句。第三句。",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=1000, text="第一句。", speaker="SPEAKER_00"),
            Segment(start_ms=1000, end_ms=1200, text="啊", speaker="SPEAKER_01"),
            Segment(start_ms=1200, end_ms=2500, text="第二句。", speaker="SPEAKER_00"),
            Segment(start_ms=2500, end_ms=4000, text="第三句。", speaker="SPEAKER_00"),
        ],
    )

    result = align_transcript_with_speakers(transcript, [])

    assert len(result.segments) == 1
    assert result.segments[0].speaker == "SPEAKER_00"
    assert "第一句" in result.segments[0].text
    assert "第三句" in result.segments[0].text


def test_align_transcript_splits_overlong_same_speaker_segments_for_readability() -> None:
    transcript = TranscriptResult(
        text="第一段。第二段。第三段。",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=8000, text="第一段。", speaker="SPEAKER_00"),
            Segment(start_ms=8000, end_ms=16000, text="第二段。", speaker="SPEAKER_00"),
            Segment(start_ms=16000, end_ms=24000, text="第三段。", speaker="SPEAKER_00"),
        ],
    )

    result = align_transcript_with_speakers(transcript, [])

    assert len(result.segments) >= 2
    assert all(segment.speaker == "SPEAKER_00" for segment in result.segments)
    assert all((segment.end_ms - segment.start_ms) <= 15000 for segment in result.segments)


def test_merge_short_segments_removes_adjacent_duplicate_phrase() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=1000, text="做到的对吧？", speaker="SPEAKER_00"),
            Segment(start_ms=1000, end_ms=2000, text="做到的对吧？", speaker="SPEAKER_00"),
        ]
    )

    assert len(result) == 1
    assert result[0].text == "做到的对吧？"


def test_merge_short_segments_absorbs_filler_fragment_between_same_speaker() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=1200, text="我们先看第一点。", speaker="SPEAKER_00"),
            Segment(start_ms=1200, end_ms=1400, text="嗯", speaker="SPEAKER_01"),
            Segment(start_ms=1400, end_ms=3000, text="然后继续往下说。", speaker="SPEAKER_00"),
        ]
    )

    assert len(result) == 1
    assert result[0].speaker == "SPEAKER_00"
    assert "我们先看第一点" in result[0].text
    assert "然后继续往下说" in result[0].text


def test_align_transcript_absorbs_longer_aba_fragment_when_middle_is_short_residue() -> None:
    transcript = TranscriptResult(
        text="第一句。中间半句。第三句。",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=2000, text="第一句。", speaker="SPEAKER_00"),
            Segment(start_ms=2000, end_ms=3900, text="半句", speaker="SPEAKER_01"),
            Segment(start_ms=3900, end_ms=6200, text="第三句。", speaker="SPEAKER_00"),
        ],
    )

    result = align_transcript_with_speakers(transcript, [])

    assert len(result.segments) == 1
    assert result.segments[0].speaker == "SPEAKER_00"


def test_build_exclusive_speaker_timeline_splits_overlap_at_midpoint() -> None:
    segments = [
        Segment(start_ms=0, end_ms=2000, text="", speaker="SPEAKER_00", confidence=0.9),
        Segment(start_ms=1500, end_ms=3000, text="", speaker="SPEAKER_01", confidence=0.95),
    ]

    exclusive = build_exclusive_speaker_timeline(segments)

    assert len(exclusive) == 2
    assert exclusive[0].speaker == "SPEAKER_00"
    assert exclusive[0].start_ms == 0
    assert exclusive[0].end_ms == 1750
    assert exclusive[1].speaker == "SPEAKER_01"
    assert exclusive[1].start_ms == 1750
    assert exclusive[1].end_ms == 3000


def test_merge_short_segments_repairs_cjk_word_split_across_same_speaker_boundary() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=9000, text="没有应用加工逻", speaker="SPEAKER_00"),
            Segment(start_ms=9000, end_ms=15000, text="辑的时候，这个场景是可以做到的。", speaker="SPEAKER_00"),
        ],
        max_merged_duration_ms=10000,
    )

    assert len(result) == 2
    assert result[0].text == "没有应用加工"
    assert result[1].text.startswith("逻辑的时候")


def test_merge_short_segments_trims_leading_punctuation_on_same_speaker_followup() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=7000, text="前面这句已经说完", speaker="SPEAKER_00"),
            Segment(start_ms=7000, end_ms=12000, text="。两周前，平台功能基本上主体OK之后", speaker="SPEAKER_00"),
        ],
        max_merged_duration_ms=10000,
    )

    assert len(result) == 2
    assert not result[1].text.startswith("。")
    assert result[1].text.startswith("两周前")


def test_merge_short_segments_drops_empty_segments_after_boundary_cleanup() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=1000, text="第一句。", speaker="SPEAKER_00"),
            Segment(start_ms=1000, end_ms=1200, text="", speaker="SPEAKER_00"),
            Segment(start_ms=1200, end_ms=2200, text="第二句。", speaker="SPEAKER_01"),
        ]
    )

    assert len(result) == 2
    assert all(segment.text for segment in result)


def test_merge_short_segments_absorbs_tiny_same_speaker_followup_fragment() -> None:
    result = merge_short_segments(
        [
            Segment(start_ms=0, end_ms=9000, text="前面主体已经说完。", speaker="SPEAKER_00"),
            Segment(start_ms=9100, end_ms=9700, text="对吧", speaker="SPEAKER_00"),
            Segment(start_ms=12000, end_ms=18000, text="后面是另一个阶段。", speaker="SPEAKER_01"),
        ],
        max_merged_duration_ms=10000,
    )

    assert len(result) == 2
    assert result[0].speaker == "SPEAKER_00"
    assert "前面主体已经说完" in result[0].text
    assert "对吧" in result[0].text


def test_build_display_speaker_timeline_merges_short_bridge_between_same_speakers() -> None:
    display = build_display_speaker_timeline(
        [
            Segment(start_ms=0, end_ms=3000, text="第一段", speaker="SPEAKER_00"),
            Segment(start_ms=3000, end_ms=3400, text="嗯", speaker="SPEAKER_01"),
            Segment(start_ms=3400, end_ms=6200, text="第二段", speaker="SPEAKER_00"),
        ]
    )

    assert len(display) == 1
    assert display[0].speaker == "SPEAKER_00"
    assert display[0].start_ms == 0
    assert display[0].end_ms == 6200
