import argparse

from scripts.smoke_api_core_pipeline import (
    build_transcription_payload,
    normalize_api_base_url,
    summarize_minutes_response,
    summarize_transcript_response,
)


def _args(**overrides):
    defaults = {
        "asr_model": "funasr-nano",
        "language": "zh-cn",
        "vad_enabled": False,
        "itn": True,
        "hotwords": [],
        "single_speaker": False,
        "diarization_model": "3dspeaker-diarization",
        "num_speakers": None,
        "min_speakers": None,
        "max_speakers": None,
        "voiceprint_scope_mode": "none",
        "voiceprint_group_id": None,
        "voiceprint_profile_ids": [],
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_normalize_api_base_url_appends_version_prefix() -> None:
    assert normalize_api_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/api/v1"
    assert normalize_api_base_url("http://127.0.0.1:8000/api/v1") == "http://127.0.0.1:8000/api/v1"


def test_build_transcription_payload_defaults_to_multi_speaker() -> None:
    payload = build_transcription_payload(_args(hotwords=["分类分级"]), "sample.wav")

    assert payload["asset_name"] == "sample.wav"
    assert payload["asr_model"] == "funasr-nano"
    assert payload["diarization_model"] == "3dspeaker-diarization"
    assert payload["hotwords"] == ["分类分级"]
    assert "voiceprint_scope_mode" not in payload


def test_build_transcription_payload_can_request_voiceprint_scope() -> None:
    payload = build_transcription_payload(
        _args(
            voiceprint_scope_mode="group",
            voiceprint_group_id="team-a",
            voiceprint_profile_ids=["p1", "p2"],
            num_speakers=3,
        ),
        "sample.wav",
    )

    assert payload["voiceprint_scope_mode"] == "group"
    assert payload["voiceprint_group_id"] == "team-a"
    assert payload["voiceprint_profile_ids"] == ["p1", "p2"]
    assert payload["num_speakers"] == 3


def test_summarize_transcript_response_counts_speakers() -> None:
    summary = summarize_transcript_response(
        {
            "job": {"job_type": "multi_speaker_transcription", "status": "succeeded"},
            "transcript": {
                "text": "你好世界",
                "segments": [
                    {"speaker": "SPEAKER_01", "text": "你好"},
                    {"speaker": "SPEAKER_02", "text": "世界"},
                    {"speaker": "SPEAKER_01", "text": "继续"},
                ],
            },
        }
    )

    assert summary["text_length"] == 4
    assert summary["segment_count"] == 3
    assert summary["speaker_count"] == 2
    assert summary["speakers"] == ["SPEAKER_01", "SPEAKER_02"]


def test_summarize_minutes_response_keeps_evidence_counts() -> None:
    summary = summarize_minutes_response(
        {
            "mode": "local",
            "summary": "会议讨论分类分级。",
            "decisions": ["先做日志"],
            "action_items": ["整理规则"],
            "risks": [],
            "evidence": {
                "decisions": [{"evidence_score": 0.9}],
                "action_items": [{"evidence_score": 0.8}],
            },
        }
    )

    assert summary["mode"] == "local"
    assert summary["decision_count"] == 1
    assert summary["action_item_count"] == 1
    assert summary["risk_count"] == 0
    assert summary["evidence_counts"] == {"decisions": 1, "action_items": 1}
