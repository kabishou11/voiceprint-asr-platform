from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from domain.schemas.transcript import JobDetail, Segment, TranscriptResult

from apps.api.app.services import meeting_minutes


class _FakeMinutesResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                        "reasoning_details": [],
                    }
                }
            ]
        }


def test_llm_meeting_minutes_uses_late_long_transcript_content(monkeypatch) -> None:
    settings = SimpleNamespace(
        minutes_llm_api_key="test-key",
        minutes_llm_base_url="https://example.test/v1",
        minutes_llm_model="test-model",
        minutes_llm_reasoning_split=True,
        minutes_llm_timeout_seconds=5.0,
    )
    monkeypatch.setattr(meeting_minutes, "get_settings", lambda: settings)

    def fake_post(url, headers, json, timeout):
        content = json["messages"][-1]["content"]
        if "后半段行动项" in content:
            return _FakeMinutesResponse(
                '{"summary":"后半段被纳入","key_points":["后半段重点"],"topics":["后半段议题"],'
                '"decisions":["后半段决策"],"action_items":["后半段行动项"],"risks":[],"keywords":["后半段"]}'
            )
        return _FakeMinutesResponse(
            '{"summary":"前半段","key_points":["前半段重点"],"topics":["前半段议题"],'
            '"decisions":[],"action_items":[],"risks":[],"keywords":["前半段"]}'
        )

    monkeypatch.setattr(meeting_minutes.httpx, "post", fake_post)
    long_text = "前半段内容。" * 5000 + "后半段行动项：张三负责最终确认。"
    job = JobDetail(
        job_id="minutes-long",
        job_type="transcription",
        status="succeeded",
        asset_name="long-meeting.wav",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        result=TranscriptResult(
            text=long_text,
            language="zh-cn",
            segments=[
                Segment(start_ms=0, end_ms=1000, text=long_text[:20000], speaker="SPEAKER_00"),
                Segment(start_ms=1000, end_ms=2000, text=long_text[20000:], speaker="SPEAKER_01"),
            ],
        ),
    )

    minutes = meeting_minutes.build_llm_meeting_minutes(job)

    assert "后半段行动项" in minutes.action_items
    assert "后半段决策" in minutes.decisions
    assert minutes.evidence is not None
    assert minutes.evidence["action_items"][0]["matched"] is True
    assert minutes.evidence["action_items"][0]["speaker"] == "SPEAKER_01"


def test_local_meeting_minutes_merges_long_transcript_chunks() -> None:
    early_segments = [
        Segment(
            start_ms=index * 1000,
            end_ms=(index + 1) * 1000,
            text=f"需要前期事项{index}。{'铺垫。' * 5000}",
            speaker="SPEAKER_00",
        )
        for index in range(10)
    ]
    late_segment = Segment(
        start_ms=10000,
        end_ms=11000,
        text=f"后半段行动项：李四负责上线确认。{'补充。' * 5000}",
        speaker="SPEAKER_01",
    )
    job = JobDetail(
        job_id="minutes-local-long",
        job_type="transcription",
        status="succeeded",
        asset_name="local-long-meeting.wav",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        result=TranscriptResult(
            text="",
            language="zh-cn",
            segments=[*early_segments, late_segment],
        ),
    )

    minutes = meeting_minutes.build_meeting_minutes(job)

    assert any("后半段行动项" in item for item in minutes.action_items)
    assert minutes.evidence is not None
    assert any(item["matched"] for item in minutes.evidence["action_items"])
