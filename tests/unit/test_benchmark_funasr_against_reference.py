from scripts.benchmark_funasr_against_reference import _slice_reference_text_for_benchmark


def test_slice_reference_text_uses_sentence_ratio_when_clipping_audio_window():
    text = "第一句内容。第二句内容更长一些。第三句收尾。"

    sliced, meta = _slice_reference_text_for_benchmark(
        text,
        audio_duration_seconds=120.0,
        max_seconds=40.0,
    )

    assert sliced == "第一句内容。第二句内容更长一些。"
    assert meta["reference_slice_mode"] == "sentence_ratio"
    assert 0.0 < float(meta["reference_slice_ratio"]) < 1.0


def test_slice_reference_text_returns_full_text_when_no_clipping_requested():
    text = "完整参考稿，没有裁剪。"

    sliced, meta = _slice_reference_text_for_benchmark(
        text,
        audio_duration_seconds=120.0,
        max_seconds=None,
    )

    assert sliced == text
    assert meta["reference_slice_mode"] == "full"
    assert meta["reference_slice_length"] == len(text)
