from scripts.core_pipeline_metrics import TranscriptArtifact, TranscriptSegment
from scripts.generate_evaluation_annotation_templates import build_annotation_templates


def test_build_annotation_templates_renders_rttm_and_json_placeholders() -> None:
    artifact = TranscriptArtifact(
        text="第一句。第二句。",
        language="zh-cn",
        segments=[
            TranscriptSegment(start_ms=0, end_ms=1000, text="第一句", speaker="SPEAKER_00"),
            TranscriptSegment(start_ms=1000, end_ms=2500, text="第二句", speaker="SPEAKER_01"),
        ],
        metadata={},
    )

    templates = build_annotation_templates(artifact, sample_id="demo")

    assert "SPEAKER demo 1 0.000 1.000 <NA> <NA> SPEAKER_00 <NA> <NA>" in templates["rttm"]
    assert "SPEAKER demo 1 1.000 1.500 <NA> <NA> SPEAKER_01 <NA> <NA>" in templates["rttm"]
    assert '"SPEAKER_00"' in templates["voiceprint_labels"]
    assert '"decisions": []' in templates["minutes"]
    assert "不应直接当作人工真值" in templates["review_notes"]
