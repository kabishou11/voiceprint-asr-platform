from domain.schemas.transcript import Segment, TranscriptResult

from scripts.export_readable_transcript import (
    build_speaker_summaries,
    prepare_display_segments,
    render_readable_transcript,
)


def test_render_readable_transcript_includes_timestamps_and_speakers() -> None:
    result = TranscriptResult(
        text="你好。我们开始开会。",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=1200, text="你好。", speaker="SPEAKER_01"),
            Segment(start_ms=1200, end_ms=4800, text="我们开始开会。", speaker="SPEAKER_00"),
        ],
    )

    rendered = render_readable_transcript(result, title="demo.wav")

    assert "文件: demo.wav" in rendered
    assert "=== Speaker 汇总 ===" in rendered
    assert "- SPEAKER_00: 1 段 | 00:00:03.600" in rendered
    assert "[00:00:00.000 - 00:00:01.200 | 00:00:01.200] SPEAKER_01" in rendered
    assert "[00:00:01.200 - 00:00:04.800 | 00:00:03.600] SPEAKER_00" in rendered
    assert "我们开始开会。" in rendered
    assert "=== 全文 ===" not in rendered


def test_build_speaker_summaries_sorts_by_duration() -> None:
    result = TranscriptResult(
        text="a",
        language="zh-cn",
        segments=[
            Segment(start_ms=0, end_ms=1000, text="a", speaker="SPEAKER_02"),
            Segment(start_ms=1000, end_ms=5000, text="b", speaker="SPEAKER_01"),
            Segment(start_ms=5000, end_ms=7000, text="c", speaker="SPEAKER_02"),
        ],
    )

    summaries = build_speaker_summaries(result.segments)

    assert summaries[0] == ("SPEAKER_01", 1, 4000)
    assert summaries[1] == ("SPEAKER_02", 2, 3000)


def test_prepare_display_segments_hides_tiny_filler_and_remerges_for_export() -> None:
    segments = [
        Segment(start_ms=0, end_ms=1500, text="我们先看第一点。", speaker="SPEAKER_00"),
        Segment(start_ms=1500, end_ms=1900, text="嗯", speaker="SPEAKER_00"),
        Segment(start_ms=1900, end_ms=3500, text="然后继续往下说。", speaker="SPEAKER_00"),
    ]

    prepared = prepare_display_segments(segments)

    assert len(prepared) == 1
    assert prepared[0].speaker == "SPEAKER_00"
    assert "我们先看第一点" in prepared[0].text
    assert "然后继续往下说" in prepared[0].text
