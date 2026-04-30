from scripts.core_pipeline_metrics import (
    TranscriptArtifact,
    TranscriptSegment,
    _parse_readable_transcript,
    build_core_pipeline_report,
    character_error_rate,
    diarization_error_metrics,
    hotword_recall,
    minutes_coverage_diagnostics,
    render_markdown_report,
    speaker_diagnostics,
    voiceprint_diagnostics,
    voiceprint_identification_metrics,
    voiceprint_probe_diagnostics,
    voiceprint_threshold_scan,
)


def test_character_error_rate_normalizes_chinese_punctuation() -> None:
    assert (
        character_error_rate("分类分级准确率超过百分之九十。", "分类分级准确率超过百分之九十")
        == 0.0
    )
    assert character_error_rate("分类分级", "分类评级") == 0.25


def test_hotword_recall_reports_missing_terms() -> None:
    result = hotword_recall(["联社", "分类分级", "江南"], "联社分类分级准确率超过九十。")

    assert result["available"] is True
    assert result["matched"] == 2
    assert result["recall"] == 2 / 3
    assert result["missing"] == ["江南"]


def test_parse_readable_transcript_extracts_segments_and_language() -> None:
    artifact = _parse_readable_transcript(
        "\n".join(
            [
                "文件: demo",
                "语言: unknown",
                "=== 分段 ===",
                "0001. [00:00:00.000 - 00:00:02.500 | 00:00:02.500] SPEAKER_00",
                "第一句话。",
                "0002. [00:00:02.500 - 00:00:04.000 | 00:00:01.500] SPEAKER_01",
                "第二句话。",
            ]
        )
    )

    assert artifact.language == "unknown"
    assert len(artifact.segments) == 2
    assert artifact.segments[0].end_ms == 2500
    assert artifact.segments[1].speaker == "SPEAKER_01"
    assert "第二句话" in artifact.text


def test_speaker_diagnostics_flags_fragments_and_turns() -> None:
    segments = [
        TranscriptSegment(start_ms=0, end_ms=1000, text="短段", speaker="SPEAKER_00"),
        TranscriptSegment(start_ms=1000, end_ms=4000, text="正常段", speaker="SPEAKER_01"),
        TranscriptSegment(start_ms=4000, end_ms=22000, text="长段", speaker="SPEAKER_01"),
    ]

    result = speaker_diagnostics(segments, short_fragment_ms=1500, long_segment_ms=15000)

    assert result["speaker_count"] == 2
    assert result["short_fragment_count"] == 1
    assert result["long_segment_count"] == 1
    assert result["speaker_turn_count"] == 1
    assert result["text_segment_count"] == 3
    assert result["text_coverage_ratio"] == 1.0
    assert result["readability_available"] is True


def test_speaker_diagnostics_flags_readability_boundary_issues() -> None:
    segments = [
        TranscriptSegment(start_ms=0, end_ms=9000, text="没有应用加工逻", speaker="SPEAKER_00"),
        TranscriptSegment(
            start_ms=9000,
            end_ms=15000,
            text="辑的时候，这个场景是可以做到的。",
            speaker="SPEAKER_01",
        ),
        TranscriptSegment(
            start_ms=15000,
            end_ms=18000,
            text="。两周前继续说",
            speaker="SPEAKER_01",
        ),
    ]

    result = speaker_diagnostics(segments)

    assert result["cjk_split_boundary_count"] == 1
    assert result["cjk_split_boundary_examples"][0]["boundary_ms"] == 9000
    assert result["leading_punctuation_count"] == 1
    assert result["leading_punctuation_examples"][0]["start_ms"] == 15000


def test_speaker_diagnostics_does_not_flag_repaired_cjk_boundary() -> None:
    segments = [
        TranscriptSegment(start_ms=0, end_ms=5000, text="没有应用加工", speaker="SPEAKER_00"),
        TranscriptSegment(
            start_ms=5000,
            end_ms=15000,
            text="逻辑的时候，这个场景是可以做到的。",
            speaker="SPEAKER_01",
        ),
    ]

    result = speaker_diagnostics(segments)

    assert result["cjk_split_boundary_count"] == 0


def test_render_markdown_report_includes_speaker_readability_ratios() -> None:
    markdown = render_markdown_report(
        {
            "speakers": {
                "speaker_count": 2,
                "segment_count": 3,
                "short_fragment_ratio": 0.1,
                "speaker_turns_per_minute": 2.0,
                "long_segment_count": 0,
                "cjk_split_boundary_count": 1,
                "cjk_split_boundary_ratio": 0.5,
                "leading_punctuation_count": 1,
                "leading_punctuation_ratio": 1 / 3,
            },
        }
    )

    assert "- 中文断词边界率: 50.00%" in markdown
    assert "- 前导标点段率: 33.33%" in markdown


def test_voiceprint_diagnostics_uses_metadata_matches() -> None:
    metadata = {
        "voiceprint_matches": [
            {
                "speaker": "SPEAKER_00",
                "matched": True,
                "candidates": [{"profile_id": "p1", "score": 0.91}],
            },
            {
                "speaker": "SPEAKER_01",
                "matched": False,
                "candidates": [{"profile_id": "p2", "score": 0.42}],
            },
        ]
    }

    result = voiceprint_diagnostics(metadata, low_confidence_threshold=0.65)

    assert result["matched_speaker_count"] == 1
    assert result["unmatched_speaker_count"] == 1
    assert result["low_confidence_speakers"] == ["SPEAKER_01"]


def test_voiceprint_probe_diagnostics_flags_risky_speaker_segments() -> None:
    segments = [
        TranscriptSegment(start_ms=0, end_ms=3000, text="干净长句", speaker="SPEAKER_00"),
        TranscriptSegment(start_ms=4000, end_ms=8000, text="重叠长句", speaker="SPEAKER_00"),
        TranscriptSegment(start_ms=4500, end_ms=7500, text="重叠讲话", speaker="SPEAKER_01"),
        TranscriptSegment(start_ms=8200, end_ms=9000, text="短句", speaker="SPEAKER_01"),
    ]

    result = voiceprint_probe_diagnostics(segments, min_probe_duration_ms=2000)

    assert result["available"] is True
    assert result["probe_ready_count"] == 1
    assert result["risky_speakers"] == ["SPEAKER_01"]
    assert result["by_speaker"]["SPEAKER_00"]["probe_ready"] is True
    assert result["by_speaker"]["SPEAKER_01"]["overlapped_segment_count"] == 1


def test_diarization_error_metrics_maps_speaker_labels() -> None:
    reference = [
        TranscriptSegment(start_ms=0, end_ms=1000, text="", speaker="alice"),
        TranscriptSegment(start_ms=1000, end_ms=2000, text="", speaker="bob"),
    ]
    hypothesis = [
        TranscriptSegment(start_ms=0, end_ms=1000, text="", speaker="SPEAKER_01"),
        TranscriptSegment(start_ms=1000, end_ms=2000, text="", speaker="SPEAKER_00"),
    ]

    result = diarization_error_metrics(reference, hypothesis, frame_step_ms=500)

    assert result["available"] is True
    assert result["der"] == 0.0
    assert result["jer"] == 0.0
    assert result["speaker_mapping"] == {"SPEAKER_01": "alice", "SPEAKER_00": "bob"}


def test_diarization_error_metrics_counts_miss_and_false_alarm() -> None:
    reference = [TranscriptSegment(start_ms=0, end_ms=1000, text="", speaker="alice")]
    hypothesis = [TranscriptSegment(start_ms=1000, end_ms=2000, text="", speaker="SPEAKER_00")]

    result = diarization_error_metrics(reference, hypothesis, frame_step_ms=500)

    assert result["der"] == 2.0
    assert result["miss_rate"] == 1.0
    assert result["false_alarm_rate"] == 1.0


def test_voiceprint_threshold_scan_estimates_eer() -> None:
    metadata = {
        "voiceprint_matches": [
            {
                "speaker": "SPEAKER_00",
                "candidates": [
                    {"profile_id": "alice", "display_name": "Alice", "score": 0.9},
                    {"profile_id": "bob", "display_name": "Bob", "score": 0.4},
                ],
            },
            {
                "speaker": "SPEAKER_01",
                "candidates": [
                    {"profile_id": "bob", "display_name": "Bob", "score": 0.8},
                    {"profile_id": "alice", "display_name": "Alice", "score": 0.3},
                ],
            },
        ]
    }

    result = voiceprint_threshold_scan(
        metadata,
        {"SPEAKER_00": "alice", "SPEAKER_01": "bob"},
        thresholds=[0.5, 0.85],
    )

    assert result["available"] is True
    assert result["positive_count"] == 2
    assert result["negative_count"] == 2
    assert result["approx_eer"]["threshold"] == 0.5
    assert result["approx_eer"]["eer"] == 0.0


def test_voiceprint_threshold_scan_counts_missing_positive_as_false_negative() -> None:
    metadata = {
        "voiceprint_matches": [
            {
                "speaker": "SPEAKER_00",
                "candidates": [
                    {"profile_id": "bob", "display_name": "Bob", "score": 0.92},
                ],
            },
            {
                "speaker": "SPEAKER_01",
                "candidates": [],
            },
        ]
    }

    result = voiceprint_threshold_scan(
        metadata,
        {"SPEAKER_00": "alice", "SPEAKER_01": "carol"},
        thresholds=[0.0, 0.5],
    )

    assert result["available"] is True
    assert result["missing_positive_count"] == 2
    assert result["missing_positive_speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert result["approx_eer"]["eer"] > 0.0
    assert result["roc_points"][0]["fn"] == 2
    assert result["score_rows"][0]["profile_id"] == "bob"
    assert result["score_rows"][1]["missing_positive"] is True
    assert result["score_rows"][1]["score"] is None


def test_voiceprint_threshold_scan_counts_missing_result_as_false_negative() -> None:
    metadata = {
        "voiceprint_matches": [
            {
                "speaker": "SPEAKER_00",
                "candidates": [
                    {"profile_id": "alice", "display_name": "Alice", "score": 0.9},
                ],
            }
        ]
    }

    result = voiceprint_threshold_scan(
        metadata,
        {"SPEAKER_00": "alice", "SPEAKER_01": "bob"},
        thresholds=[0.0, 0.5],
    )

    assert result["available"] is True
    assert result["positive_count"] == 2
    assert result["missing_result_count"] == 1
    assert result["missing_result_speakers"] == ["SPEAKER_01"]
    assert result["missing_positive_speakers"] == ["SPEAKER_01"]
    assert result["approx_eer"]["eer"] > 0.0
    assert result["roc_points"][0]["fn"] == 1
    assert result["score_rows"][1]["missing_result"] is True
    assert result["score_rows"][1]["missing_positive"] is True


def test_voiceprint_threshold_scan_evaluates_empty_matches_as_all_missing() -> None:
    result = voiceprint_threshold_scan(
        {"voiceprint_matches": []},
        {"SPEAKER_00": "alice", "SPEAKER_01": "bob"},
        thresholds=[0.0, 0.5],
    )

    assert result["available"] is True
    assert result["sample_count"] == 2
    assert result["positive_count"] == 2
    assert result["missing_result_count"] == 2
    assert result["missing_result_speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert result["missing_positive_count"] == 2
    assert result["roc_points"][0]["fn"] == 2


def test_voiceprint_identification_metrics_reports_topk_and_missing_positive() -> None:
    metadata = {
        "voiceprint_matches": [
            {
                "speaker": "SPEAKER_00",
                "candidates": [
                    {"profile_id": "bob", "display_name": "Bob", "score": 0.91},
                    {"profile_id": "alice", "display_name": "Alice", "score": 0.82},
                ],
            },
            {
                "speaker": "SPEAKER_01",
                "candidates": [
                    {"profile_id": "carol", "display_name": "Carol", "score": 0.88},
                ],
            },
        ]
    }

    result = voiceprint_identification_metrics(
        metadata,
        {"SPEAKER_00": "alice", "SPEAKER_01": "dave", "SPEAKER_02": "erin"},
        top_k=2,
    )

    assert result["available"] is True
    assert result["top1_accuracy"] == 0.0
    assert result["topk_accuracy"] == 1 / 3
    assert result["missing_result_speakers"] == ["SPEAKER_02"]
    assert result["missing_positive_speakers"] == ["SPEAKER_01", "SPEAKER_02"]
    assert result["rows"][0]["topk_hit"] is True


def test_voiceprint_identification_metrics_evaluates_empty_matches_as_all_missing() -> None:
    result = voiceprint_identification_metrics(
        {"voiceprint_matches": []},
        {"SPEAKER_00": "alice", "SPEAKER_01": "bob"},
        top_k=2,
    )

    assert result["available"] is True
    assert result["top1_accuracy"] == 0.0
    assert result["topk_accuracy"] == 0.0
    assert result["missing_result_count"] == 2
    assert result["missing_result_speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert result["missing_positive_count"] == 2


def test_minutes_coverage_finds_evidence_in_transcript() -> None:
    minutes = {
        "decisions": ["决定先做日志分类分级"],
        "action_items": ["李四负责上线确认"],
        "risks": ["外部文档未覆盖"],
    }
    transcript = "会议决定先做日志分类分级。后续李四负责上线确认。"

    result = minutes_coverage_diagnostics(minutes, transcript)

    assert result["decisions"]["coverage"] == 1.0
    assert result["action_items"]["coverage"] == 1.0
    assert result["risks"]["coverage"] == 0.0
    assert result["decisions"]["evidence_rows"][0]["matched"] is True
    assert result["decisions"]["evidence_rows"][0]["reason"] == "exact_match"
    assert "会议决定先做日志分类分级" in result["decisions"]["evidence_rows"][0]["evidence_snippet"]
    assert result["risks"]["missing"] == ["外部文档未覆盖"]
    assert result["risks"]["missing_count"] == 1


def test_minutes_coverage_reports_weak_evidence_details() -> None:
    minutes = {
        "decisions": ["决定推进日志敏感字段治理并完成上线验收"],
        "action_items": [],
        "risks": [],
    }
    transcript = "会议决定先推进日志治理，但敏感字段范围还没有最终确认。"

    result = minutes_coverage_diagnostics(minutes, transcript)

    decision = result["decisions"]
    assert decision["coverage"] == 0.0
    assert decision["missing_count"] == 1
    assert decision["low_evidence_count"] == 1
    assert decision["low_evidence"][0]["item"] == "决定推进日志敏感字段治理并完成上线验收"
    assert decision["low_evidence"][0]["reason"] == "weak_token_overlap"
    assert decision["low_evidence"][0]["evidence_score"] > 0
    assert "日志治理" in decision["low_evidence"][0]["evidence_snippet"]


def test_minutes_coverage_keeps_empty_sections_compatible() -> None:
    result = minutes_coverage_diagnostics({"decisions": []}, "没有纪要条目。")

    assert result["decisions"]["coverage"] is None
    assert result["decisions"]["missing"] == []
    assert result["decisions"]["missing_count"] == 0
    assert result["decisions"]["low_evidence"] == []
    assert result["decisions"]["evidence_rows"] == []


def test_build_core_pipeline_report_combines_all_sections() -> None:
    artifact = TranscriptArtifact(
        text="联社分类分级准确率超过九十。",
        language="zh-cn",
        segments=[
            TranscriptSegment(start_ms=0, end_ms=2000, text="联社分类分级", speaker="SPEAKER_00"),
        ],
        metadata={},
    )

    report = build_core_pipeline_report(
        transcript=artifact,
        reference_text="联社分类分级准确率超过九十。",
        hotwords=["联社"],
        minutes_payload=None,
        reference_speaker_segments=[
            TranscriptSegment(start_ms=0, end_ms=2000, text="", speaker="SPEAKER_00"),
        ],
    )

    assert report["asr"]["cer"] == 0.0
    assert report["speakers"]["speaker_count"] == 1
    assert report["speaker_reference"]["der"] == 0.0
    assert report["timeline_diagnostics"]["best_source"] == "final"
    assert report["voiceprint"]["available"] is False


def test_build_core_pipeline_report_compares_metadata_timelines() -> None:
    reference = [
        TranscriptSegment(start_ms=0, end_ms=2000, text="", speaker="alice"),
        TranscriptSegment(start_ms=2000, end_ms=4000, text="", speaker="bob"),
    ]
    artifact = TranscriptArtifact(
        text="没有应用加工逻辑的时候，好的。",
        language="zh-cn",
        segments=[
            TranscriptSegment(start_ms=0, end_ms=2000, text="没有应用加工逻", speaker="SPEAKER_00"),
            TranscriptSegment(
                start_ms=2000,
                end_ms=4000,
                text="辑的时候，好的。",
                speaker="SPEAKER_01",
            ),
        ],
        metadata={
            "timelines": [
                {
                    "label": "Regular diarization",
                    "source": "regular",
                    "segments": [
                        {"start_ms": 0, "end_ms": 4000, "text": "", "speaker": "SPEAKER_00"},
                    ],
                },
                {
                    "label": "Exclusive alignment timeline",
                    "source": "exclusive",
                    "segments": [
                        {"start_ms": 0, "end_ms": 2000, "text": "", "speaker": "SPEAKER_00"},
                        {"start_ms": 2000, "end_ms": 4000, "text": "", "speaker": "SPEAKER_01"},
                    ],
                },
                {
                    "label": "Display speaker timeline",
                    "source": "display",
                    "segments": [
                        {"start_ms": 0, "end_ms": 4000, "text": "", "speaker": "SPEAKER_00"},
                    ],
                },
            ]
        },
    )

    report = build_core_pipeline_report(
        transcript=artifact,
        reference_speaker_segments=reference,
    )

    timeline_report = report["timeline_diagnostics"]
    by_source = {row["source"]: row for row in timeline_report["timelines"]}
    assert set(by_source) == {"regular", "exclusive", "display", "final"}
    assert by_source["exclusive"]["speaker_reference"]["der"] == 0.0
    assert by_source["final"]["speakers"]["cjk_split_boundary_count"] == 1
    assert timeline_report["best_source"] == "exclusive"


def test_timeline_diagnostics_does_not_prefer_textless_timeline_without_reference() -> None:
    artifact = TranscriptArtifact(
        text="没有应用加工逻辑的时候。",
        language="zh-cn",
        segments=[
            TranscriptSegment(start_ms=0, end_ms=2000, text="没有应用加工逻", speaker="SPEAKER_00"),
            TranscriptSegment(start_ms=2000, end_ms=4000, text="辑的时候。", speaker="SPEAKER_01"),
        ],
        metadata={
            "timelines": [
                {
                    "label": "Regular diarization",
                    "source": "regular",
                    "segments": [
                        {"start_ms": 0, "end_ms": 4000, "text": "", "speaker": "SPEAKER_00"},
                    ],
                }
            ]
        },
    )

    report = build_core_pipeline_report(transcript=artifact)
    by_source = {
        row["source"]: row
        for row in report["timeline_diagnostics"]["timelines"]
    }

    assert by_source["regular"]["speakers"]["readability_available"] is False
    assert by_source["regular"]["quality_score"] == 999.0
    assert by_source["final"]["speakers"]["text_coverage_ratio"] == 1.0
    assert report["timeline_diagnostics"]["best_source"] == "final"


def test_timeline_diagnostics_penalizes_partial_text_coverage_without_reference() -> None:
    artifact = TranscriptArtifact(
        text="分类分级规则已经确认。",
        language="zh-cn",
        segments=[
            TranscriptSegment(
                start_ms=0,
                end_ms=4000,
                text="分类分级规则已经确认。",
                speaker="SPEAKER_00",
            ),
        ],
        metadata={
            "timelines": [
                {
                    "label": "Partial display timeline",
                    "source": "display",
                    "segments": [
                        {
                            "start_ms": 0,
                            "end_ms": 2000,
                            "text": "分类分级规则",
                            "speaker": "SPEAKER_00",
                        },
                        {"start_ms": 2000, "end_ms": 4000, "text": "", "speaker": "SPEAKER_00"},
                    ],
                }
            ]
        },
    )

    report = build_core_pipeline_report(transcript=artifact)
    by_source = {
        row["source"]: row
        for row in report["timeline_diagnostics"]["timelines"]
    }

    assert by_source["display"]["speakers"]["text_coverage_ratio"] == 0.5
    assert by_source["display"]["quality_score"] == 0.5
    assert by_source["final"]["quality_score"] == 0.0
    assert report["timeline_diagnostics"]["best_source"] == "final"


def test_render_markdown_report_includes_timeline_diagnostics() -> None:
    markdown = render_markdown_report(
        {
            "timeline_diagnostics": {
                "available": True,
                "best_source": "exclusive",
                "best_quality_score": 0.01,
                "timelines": [
                    {
                        "source": "exclusive",
                        "segment_count": 2,
                        "quality_score": 0.01,
                        "speakers": {
                            "text_coverage_ratio": 1.0,
                            "short_fragment_ratio": 0.0,
                            "cjk_split_boundary_ratio": 0.0,
                            "leading_punctuation_ratio": 0.0,
                        },
                        "speaker_reference": {"der": 0.0, "jer": 0.0},
                    }
                ],
            }
        }
    )

    assert "## Timeline 诊断" in markdown
    assert "- 推荐 Timeline: exclusive" in markdown
    assert (
        "| exclusive | 2 | 0.00% | 0.00% | 100.00% | "
        "0.00% | 0.00% | 0.00% | 0.01 |"
    ) in markdown


def test_render_markdown_report_includes_voiceprint_threshold_missing_speakers() -> None:
    markdown = render_markdown_report(
        {
            "voiceprint_threshold_scan": {
                "available": True,
                "sample_count": 2,
                "missing_positive_count": 1,
                "missing_positive_speakers": ["SPEAKER_01"],
                "approx_eer": {"eer": 0.5, "threshold": 0.7},
            },
            "voiceprint_identification": {},
        }
    )

    assert "- 阈值扫描缺失正确候选: 1" in markdown
    assert "- 阈值扫描缺失 speaker: SPEAKER_01" in markdown
