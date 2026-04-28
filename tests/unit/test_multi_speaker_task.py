from apps.worker.app.tasks import multi_speaker
from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters import AudioAsset


class _DummyAsrAdapter:
    def __init__(self) -> None:
        self.hotwords = []
        self.language = "zh-cn"
        self.vad_enabled = True
        self.itn = True

    def transcribe(self, asset: AudioAsset) -> TranscriptResult:
        return TranscriptResult(
            text="甲方先说，乙方再说。",
            language="zh-cn",
            segments=[Segment(start_ms=0, end_ms=4000, text="甲方先说，乙方再说。", speaker=None)],
        )


class _DummyDiarizationAdapter:
    def __init__(self) -> None:
        self.num_speakers = None
        self.min_speakers = None
        self.max_speakers = None

    def diarize(self, asset: AudioAsset) -> list[Segment]:
        return [
            Segment(start_ms=0, end_ms=2200, text="", speaker="SPEAKER_00", confidence=0.9),
            Segment(start_ms=1800, end_ms=4000, text="", speaker="SPEAKER_01", confidence=0.95),
        ]


class _DummyVoiceprintAdapter:
    def identify(self, asset: AudioAsset, top_k: int, profile_ids: list[str] | None = None):
        from domain.schemas.voiceprint import VoiceprintIdentificationCandidate, VoiceprintIdentificationResult

        candidates = [
            VoiceprintIdentificationCandidate(
                profile_id=(profile_ids or ["profile-a"])[0],
                display_name="profile-a",
                score=0.88,
                rank=1,
            )
        ]
        return VoiceprintIdentificationResult(candidates=candidates, matched=True)


class _DummyRegistry:
    def require_available(self, model_key: str) -> None:
        return None

    def get_asr(self, model_key: str) -> _DummyAsrAdapter:
        return _DummyAsrAdapter()

    def get_diarization(self, model_key: str) -> _DummyDiarizationAdapter:
        return _DummyDiarizationAdapter()

    def get_voiceprint(self, model_key: str) -> _DummyVoiceprintAdapter:
        return _DummyVoiceprintAdapter()


def test_run_multi_speaker_transcription_attaches_timeline_metadata(monkeypatch) -> None:
    monkeypatch.setattr(multi_speaker, "get_worker_registry", lambda: _DummyRegistry())
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(multi_speaker, "_adapter_asset", lambda asset_name: AudioAsset(path=asset_name))

    result = multi_speaker.run_multi_speaker_transcription(job_id="job-1", asset_name="demo.wav")

    assert result.metadata is not None
    assert result.metadata.alignment_source == "exclusive"
    assert result.metadata.diarization_model == "3dspeaker-diarization"
    assert len(result.metadata.timelines) == 3
    assert result.metadata.timelines[0].source == "regular"
    assert result.metadata.timelines[1].source == "exclusive"
    assert result.metadata.timelines[2].source == "display"


def test_run_multi_speaker_transcription_attaches_voiceprint_matches(monkeypatch) -> None:
    from apps.api.app.services import job_db

    profile_id = "unit-profile-scope"
    group_id = "unit-group-scope"
    with job_db.session() as db:
        db.merge(job_db.VoiceprintProfileRecord(
            profile_id=profile_id,
            display_name="测试候选人",
            model_key="3dspeaker-embedding",
            sample_count=1,
        ))
        db.merge(job_db.VoiceprintGroupRecord(group_id=group_id, display_name="测试分组"))
        db.merge(job_db.VoiceprintGroupMemberRecord(group_id=group_id, profile_id=profile_id))
        db.commit()

    monkeypatch.setattr(multi_speaker, "get_worker_registry", lambda: _DummyRegistry())
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(multi_speaker, "_adapter_asset", lambda asset_name: AudioAsset(path=asset_name))
    monkeypatch.setattr(
        multi_speaker,
        "_build_speaker_probe_assets",
        lambda asset, segments, speakers, tmpdir: [
            (speaker, AudioAsset(path=f"{speaker}.wav"))
            for speaker in speakers
        ],
    )

    result = multi_speaker.run_multi_speaker_transcription(
        job_id="job-voiceprint",
        asset_name="demo.wav",
        voiceprint_scope_mode="group",
        voiceprint_group_id=group_id,
    )

    assert result.metadata is not None
    assert result.metadata.voiceprint_matches
    assert result.metadata.voiceprint_matches[0].candidate_profile_ids == [profile_id]
    assert result.metadata.voiceprint_matches[0].candidates[0].display_name == "测试候选人"
