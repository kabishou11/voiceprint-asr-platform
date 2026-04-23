from pathlib import Path

from scripts.run_reference_hotword_window_benchmark import _build_summary_payload


def test_build_summary_payload_computes_ratio_delta() -> None:
    payload = _build_summary_payload(
        audio=Path("audio.wav"),
        reference_text=Path("reference.txt"),
        window_seconds=900.0,
        hotwords=["联社", "分类分级"],
        baseline_report={"sequence_ratio": 0.84, "_path": "baseline.json"},
        hotword_report={"sequence_ratio": 0.845, "_path": "hotword.json"},
    )

    assert payload["baseline_ratio"] == 0.84
    assert payload["hotword_ratio"] == 0.845
    assert payload["ratio_delta"] == 0.0050000000000000044
    assert payload["hotwords"] == ["联社", "分类分级"]
