from scripts.extract_hotwords_from_reference import extract_hotwords


def test_extract_hotwords_prioritizes_reference_only_domain_terms() -> None:
    reference = "联社分类分级要对数据资产、影像平台和代码仓库统一治理，陈涛已经提过。"
    baseline = "分类分级要对数据资产统一治理。"

    hotwords = extract_hotwords(reference, limit=20, baseline_text=baseline)

    assert "联社" in hotwords
    assert "影像平台" in hotwords
    assert "代码仓库" in hotwords
    assert "陈涛" in hotwords
