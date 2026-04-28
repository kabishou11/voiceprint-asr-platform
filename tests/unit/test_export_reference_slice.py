from scripts.export_reference_slice import build_reference_slice


def test_build_reference_slice_records_ratio_metadata() -> None:
    sliced, metadata = build_reference_slice(
        "第一句。第二句更长一些。第三句收尾。",
        audio_duration_seconds=120.0,
        max_seconds=40.0,
    )

    assert sliced == "第一句。第二句更长一些。"
    assert metadata["reference_slice_mode"] == "time_ratio"
    assert metadata["reference_slice_ratio"] == 1 / 3
    assert metadata["reference_full_length"] > metadata["reference_slice_length"]


def test_build_reference_slice_keeps_full_text_without_window() -> None:
    text = "完整参考稿。"

    sliced, metadata = build_reference_slice(
        text,
        audio_duration_seconds=120.0,
        max_seconds=None,
    )

    assert sliced == text
    assert metadata["reference_slice_mode"] == "full"
    assert metadata["reference_slice_ratio"] == 1.0
