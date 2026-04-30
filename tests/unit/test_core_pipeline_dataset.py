import json
from pathlib import Path

import pytest

from scripts.core_pipeline_metrics import (
    aggregate_core_pipeline_reports,
    build_baseline_comparison_report,
    build_core_pipeline_dataset_report,
    load_dataset_manifest,
    render_baseline_comparison_markdown,
    render_dataset_markdown_report,
)


def test_dataset_manifest_resolves_relative_paths_and_builds_aggregate(tmp_path: Path) -> None:
    transcript = tmp_path / "hypothesis.txt"
    transcript.write_text(
        "\n".join(
            [
                "语言: zh-cn",
                "0001. [00:00:00.000 - 00:00:01.000 | 00:00:01.000] SPEAKER_00",
                "联社分类分级。",
                "0002. [00:00:01.000 - 00:00:02.000 | 00:00:01.000] SPEAKER_01",
                "李四负责上线确认。",
            ]
        ),
        encoding="utf-8",
    )
    reference_text = tmp_path / "reference.txt"
    reference_text.write_text("联社分类分级。李四负责上线确认。", encoding="utf-8")
    reference_speakers = tmp_path / "reference.rttm"
    reference_speakers.write_text(
        "\n".join(
            [
                "SPEAKER sample 1 0.000 1.000 <NA> <NA> alice <NA> <NA>",
                "SPEAKER sample 1 1.000 1.000 <NA> <NA> bob <NA> <NA>",
            ]
        ),
        encoding="utf-8",
    )
    hotwords = tmp_path / "hotwords.txt"
    hotwords.write_text("联社\n上线确认\n", encoding="utf-8")
    minutes = tmp_path / "minutes.json"
    minutes.write_text(
        json.dumps(
            {
                "decisions": ["分类分级"],
                "action_items": ["李四负责上线确认"],
                "risks": ["外部文档未覆盖"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "suite_name": "demo_suite",
                "version": "v1",
                "samples": [
                    {
                        "name": "sample_1",
                        "transcript": transcript.name,
                        "reference_text": reference_text.name,
                        "reference_speakers": reference_speakers.name,
                        "hotwords_file": hotwords.name,
                        "minutes_json": minutes.name,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = load_dataset_manifest(manifest_path)
    report = build_core_pipeline_dataset_report(manifest, speaker_frame_step_ms=500)

    assert manifest["samples"][0]["transcript"] == str(transcript.resolve())
    assert report["suite"]["sample_count"] == 1
    assert report["aggregate"]["asr"]["mean_cer"] == 0.0
    assert report["aggregate"]["speaker_reference"]["mean_der"] == 0.0
    assert report["aggregate"]["minutes"]["mean_action_item_coverage"] == 1.0


def test_dataset_manifest_excludes_draft_reference_from_asr_aggregate(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "hypothesis.txt"
    transcript.write_text(
        "\n".join(
            [
                "语言: zh-cn",
                "0001. [00:00:00.000 - 00:00:01.000 | 00:00:01.000] SPEAKER_00",
                "真实前十五分钟文本。",
            ]
        ),
        encoding="utf-8",
    )
    reference_text = tmp_path / "reference.txt"
    reference_text.write_text("按时长比例切出来但未人工对齐的参考稿。", encoding="utf-8")
    reference_metadata = tmp_path / "reference.json"
    reference_metadata.write_text(
        json.dumps(
            {
                "reference_slice_mode": "time_ratio",
                "reference_quality": "draft_time_ratio",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "suite_name": "draft_reference_suite",
                "samples": [
                    {
                        "name": "sample_1",
                        "transcript": transcript.name,
                        "reference_text": reference_text.name,
                        "reference_metadata": reference_metadata.name,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_core_pipeline_dataset_report(load_dataset_manifest(manifest_path))
    sample = report["samples"][0]

    assert report["aggregate"]["asr"]["available_count"] == 0
    assert report["aggregate"]["asr"]["mean_cer"] is None
    assert sample["asr"]["available"] is False
    assert sample["asr_diagnostic"]["available"] is True
    assert sample["reference_text"]["quality"] == "draft_time_ratio"
    assert sample["reference_text"]["use_for_metrics"] is False


def test_dataset_manifest_allows_explicitly_confirmed_reference(tmp_path: Path) -> None:
    transcript = tmp_path / "hypothesis.txt"
    transcript.write_text(
        "\n".join(
            [
                "语言: zh-cn",
                "0001. [00:00:00.000 - 00:00:01.000 | 00:00:01.000] SPEAKER_00",
                "人工对齐文本。",
            ]
        ),
        encoding="utf-8",
    )
    reference_text = tmp_path / "reference.txt"
    reference_text.write_text("人工对齐文本。", encoding="utf-8")
    reference_metadata = tmp_path / "reference.json"
    reference_metadata.write_text(
        json.dumps({"reference_slice_mode": "time_ratio"}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "suite_name": "confirmed_reference_suite",
                "samples": [
                    {
                        "name": "sample_1",
                        "transcript": transcript.name,
                        "reference_text": reference_text.name,
                        "reference_metadata": reference_metadata.name,
                        "reference_quality": "confirmed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_core_pipeline_dataset_report(load_dataset_manifest(manifest_path))

    assert report["aggregate"]["asr"]["available_count"] == 1
    assert report["aggregate"]["asr"]["mean_cer"] == 0.0
    assert report["samples"][0]["reference_text"]["use_for_metrics"] is True


def test_render_dataset_markdown_includes_sample_table() -> None:
    report = {
        "suite": {"name": "demo", "version": "v1", "sample_count": 1},
        "aggregate": {
            "asr": {"mean_cer": 0.1, "mean_sequence_ratio": 0.9, "mean_hotword_recall": None},
            "speakers": {"mean_speaker_count": 2, "mean_short_fragment_ratio": 0.2},
            "speaker_reference": {"mean_der": 0.3, "mean_jer": 0.4},
            "timeline_diagnostics": {
                "mean_best_quality_score": 0.12,
                "best_source_counts": {"exclusive": 1},
                "sources": {
                    "exclusive": {
                        "available_count": 1,
                        "mean_segment_count": 2,
                        "mean_der": 0.3,
                        "mean_jer": 0.4,
                        "mean_short_fragment_ratio": 0.2,
                        "mean_cjk_split_boundary_ratio": 0.1,
                        "mean_leading_punctuation_ratio": 0.0,
                        "mean_quality_score": 0.12,
                    }
                },
            },
            "voiceprint_probe": {"mean_probe_ready_ratio": 0.6},
            "voiceprint_threshold_scan": {"mean_approx_eer": 0.15},
            "voiceprint_identification": {
                "mean_top1_accuracy": 0.7,
                "mean_topk_accuracy": 0.9,
            },
            "minutes": {
                "mean_decision_coverage": 1.0,
                "mean_action_item_coverage": 0.5,
                "mean_risk_coverage": None,
            },
        },
        "samples": [
            {
                "sample": {"name": "sample_1"},
                "asr": {"cer": 0.1},
                "speaker_reference": {"der": 0.3, "jer": 0.4},
                "voiceprint_probe": {"probe_ready_ratio": 0.6},
                "voiceprint_threshold_scan": {"approx_eer": {"eer": 0.15}},
                "voiceprint_identification": {
                    "top1_accuracy": 0.7,
                    "topk_accuracy": 0.9,
                },
                "minutes": {
                    "decisions": {"coverage": 1.0},
                    "action_items": {"coverage": 0.5},
                    "risks": {"coverage": None},
                },
            }
        ],
    }

    markdown = render_dataset_markdown_report(report)

    assert "# 核心流水线样本集基线报告" in markdown
    assert "- 推荐 Timeline 分布: exclusive=1" in markdown
    assert "| exclusive | 1 | 2.00 | 30.00% | 40.00% | 20.00% | 10.00% | 0.00% | 0.12 |" in markdown
    assert (
        "| sample_1 | 10.00% | 30.00% | 40.00% | 15.00% | "
        "70.00% | 90.00% | 100.00% | 50.00% | N/A |"
    ) in markdown


def test_aggregate_core_pipeline_reports_summarizes_timeline_diagnostics() -> None:
    samples = [
        {
            "timeline_diagnostics": {
                "available": True,
                "best_source": "exclusive",
                "best_quality_score": 0.1,
                "timelines": [
                    {
                        "source": "exclusive",
                        "segment_count": 2,
                        "quality_score": 0.1,
                        "speaker_reference": {"der": 0.0, "jer": 0.2},
                        "speakers": {
                            "short_fragment_ratio": 0.1,
                            "cjk_split_boundary_ratio": 0.0,
                            "leading_punctuation_ratio": 0.0,
                        },
                    },
                    {
                        "source": "display",
                        "segment_count": 1,
                        "quality_score": 0.5,
                        "speaker_reference": {"der": 0.4, "jer": 0.4},
                        "speakers": {
                            "short_fragment_ratio": 0.0,
                            "cjk_split_boundary_ratio": 0.0,
                            "leading_punctuation_ratio": 0.0,
                        },
                    },
                ],
            }
        },
        {
            "timeline_diagnostics": {
                "available": True,
                "best_source": "exclusive",
                "best_quality_score": 0.2,
                "timelines": [
                    {
                        "source": "exclusive",
                        "segment_count": 4,
                        "quality_score": 0.2,
                        "speaker_reference": {"der": 0.2, "jer": 0.2},
                        "speakers": {
                            "short_fragment_ratio": 0.2,
                            "cjk_split_boundary_ratio": 0.1,
                            "leading_punctuation_ratio": 0.0,
                        },
                    }
                ],
            }
        },
    ]

    aggregate = aggregate_core_pipeline_reports(samples)
    timeline = aggregate["timeline_diagnostics"]

    assert timeline["available_count"] == 2
    assert timeline["best_source_counts"] == {"exclusive": 2}
    assert timeline["mean_best_quality_score"] == pytest.approx(0.15)
    assert timeline["sources"]["exclusive"]["mean_segment_count"] == 3.0
    assert timeline["sources"]["exclusive"]["mean_der"] == pytest.approx(0.1)
    assert timeline["sources"]["display"]["mean_quality_score"] == 0.5


def test_baseline_comparison_reports_delta_from_first() -> None:
    first = {
        "suite": {"name": "baseline_v1", "sample_count": 1},
        "aggregate": {
            "asr": {"mean_cer": 0.2},
            "speakers": {
                "mean_cjk_split_boundary_count": 3.0,
                "mean_cjk_split_boundary_ratio": 0.3,
                "mean_leading_punctuation_count": 2.0,
                "mean_leading_punctuation_ratio": 0.2,
            },
            "speaker_reference": {"mean_der": 0.4, "mean_jer": 0.5},
            "timeline_diagnostics": {"mean_best_quality_score": 0.8},
            "voiceprint_probe": {"mean_probe_ready_ratio": 0.4},
            "voiceprint_threshold_scan": {"mean_approx_eer": 0.3},
            "voiceprint_identification": {
                "mean_top1_accuracy": 0.5,
                "mean_topk_accuracy": 0.7,
            },
            "minutes": {"mean_decision_coverage": 0.5},
        },
    }
    second = {
        "suite": {"name": "baseline_v2", "sample_count": 1},
        "aggregate": {
            "asr": {"mean_cer": 0.1},
            "speakers": {
                "mean_cjk_split_boundary_count": 1.0,
                "mean_cjk_split_boundary_ratio": 0.1,
                "mean_leading_punctuation_count": 0.5,
                "mean_leading_punctuation_ratio": 0.05,
            },
            "speaker_reference": {"mean_der": 0.25, "mean_jer": 0.35},
            "timeline_diagnostics": {"mean_best_quality_score": 0.3},
            "voiceprint_probe": {"mean_probe_ready_ratio": 0.9},
            "voiceprint_threshold_scan": {"mean_approx_eer": 0.2},
            "voiceprint_identification": {
                "mean_top1_accuracy": 0.75,
                "mean_topk_accuracy": 0.8,
            },
            "minutes": {"mean_decision_coverage": 0.75},
        },
    }

    report = build_baseline_comparison_report([first, second])
    markdown = render_baseline_comparison_markdown(report)

    assert report["comparison"]["reference"] == "baseline_v1"
    assert report["baselines"][1]["delta_from_first"]["mean_cer"] == -0.1
    assert report["baselines"][1]["delta_from_first"]["mean_cjk_split_boundary_count"] == -2.0
    assert report["baselines"][1]["delta_from_first"][
        "mean_cjk_split_boundary_ratio"
    ] == pytest.approx(-0.2)
    assert report["baselines"][1]["delta_from_first"][
        "mean_best_timeline_quality_score"
    ] == pytest.approx(-0.5)
    assert report["baselines"][1]["delta_from_first"]["mean_leading_punctuation_count"] == -1.5
    assert report["baselines"][1]["delta_from_first"][
        "mean_leading_punctuation_ratio"
    ] == pytest.approx(-0.15)
    assert report["baselines"][1]["delta_from_first"]["mean_voiceprint_probe_ready_ratio"] == 0.5
    assert report["baselines"][1]["delta_from_first"]["mean_voiceprint_top1_accuracy"] == 0.25
    assert report["baselines"][1]["delta_from_first"]["mean_decision_coverage"] == 0.25
    assert (
        "| baseline_v2 | -10.00% | -15.00% | -15.00% | -0.50 | -2.00 | -20.00% | "
        "-1.50 | -15.00% | +50.00% | -10.00% | +25.00% | +10.00% | +25.00%"
    ) in markdown
