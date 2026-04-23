from scripts.extract_hotwords_from_reference import extract_hotwords, slice_reference_text_by_ratio


def test_extract_hotwords_prioritizes_reference_only_domain_terms() -> None:
    reference = "联社分类分级要对数据资产、影像平台和代码仓库统一治理，陈涛已经提过。"
    baseline = "分类分级要对数据资产统一治理。"

    hotwords = extract_hotwords(reference, limit=20, baseline_text=baseline)

    assert "联社" in hotwords
    assert "影像平台" in hotwords
    assert "代码仓库" in hotwords
    assert "陈涛" in hotwords


def test_extract_hotwords_filters_conversational_noise_phrases() -> None:
    reference = (
        "营销平台啊，或者说文文档云平台啊，通过它的平台里面去抽取。"
        "它一定会有一些原数据对这些数据资产的描述。"
        "郭莹和朱总都提到联社分类分级。"
    )
    baseline = "平台里面去抽取一些数据资产描述，分类分级。"

    hotwords = extract_hotwords(reference, limit=20, baseline_text=baseline)

    assert "郭莹" in hotwords
    assert "朱总" in hotwords
    assert "联社" in hotwords
    assert "分类分级" in hotwords
    assert "营销平台" in hotwords
    assert "文文档云平台" not in hotwords
    assert "有一些原数据" not in hotwords
    assert "平台里面去抽取" not in hotwords


def test_slice_reference_text_by_ratio_keeps_front_window_sentences() -> None:
    text = "第一句。第二句更长一些。第三句收尾。"

    sliced = slice_reference_text_by_ratio(
        text,
        audio_duration_seconds=120.0,
        max_seconds=40.0,
    )

    assert sliced == "第一句。第二句更长一些。"
