from domain.schemas.transcript import Segment
from model_adapters.pyannote_adapter import PyannoteDiarizationAdapter


def test_pyannote_adapter_builds_exclusive_segments_from_overlap() -> None:
    adapter = PyannoteDiarizationAdapter(enabled=True)
    segments = [
        Segment(start_ms=0, end_ms=2200, text="", speaker="SPEAKER_00", confidence=0.91),
        Segment(start_ms=1800, end_ms=3600, text="", speaker="SPEAKER_01", confidence=0.95),
    ]

    exclusive = adapter._build_exclusive_segments(segments)

    assert len(exclusive) == 2
    assert exclusive[0].speaker == "SPEAKER_00"
    assert exclusive[0].end_ms == 2000
    assert exclusive[1].speaker == "SPEAKER_01"
    assert exclusive[1].start_ms == 2000


def test_pyannote_adapter_get_last_outputs_returns_copies() -> None:
    adapter = PyannoteDiarizationAdapter(enabled=True)
    adapter._last_regular_segments = [Segment(start_ms=0, end_ms=1000, text="", speaker="SPEAKER_00")]
    adapter._last_exclusive_segments = [Segment(start_ms=0, end_ms=900, text="", speaker="SPEAKER_00")]

    outputs = adapter.get_last_outputs()
    outputs["regular"][0].end_ms = 1

    assert adapter._last_regular_segments[0].end_ms == 1000
    assert adapter._last_exclusive_segments[0].end_ms == 900
