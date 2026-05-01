from domain.schemas.transcript import Segment, TranscriptResult
from model_adapters import AudioAsset

from apps.worker.app.tasks import multi_speaker


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


class _DummyDiarizationAdapterWithLastOutputs(_DummyDiarizationAdapter):
    def diarize(self, asset: AudioAsset) -> list[Segment]:
        return self.get_last_outputs()["exclusive"]

    def get_last_outputs(self) -> dict[str, list[Segment]]:
        return {
            "regular": [
                Segment(start_ms=0, end_ms=2500, text="", speaker="raw_a", confidence=0.9),
                Segment(start_ms=1500, end_ms=4000, text="", speaker="raw_b", confidence=0.95),
            ],
            "exclusive": [
                Segment(start_ms=0, end_ms=2000, text="", speaker="raw_a", confidence=0.9),
                Segment(start_ms=2000, end_ms=4000, text="", speaker="raw_b", confidence=0.95),
            ],
        }


class _DummyVoiceprintAdapter:
    def __init__(self) -> None:
        self.seen_profile_ids: list[list[str] | None] = []

    def identify(self, asset: AudioAsset, top_k: int, profile_ids: list[str] | None = None):
        from domain.schemas.voiceprint import (
            VoiceprintIdentificationCandidate,
            VoiceprintIdentificationResult,
        )

        self.seen_profile_ids.append(profile_ids)
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
    def __init__(
        self,
        voiceprint_adapter: _DummyVoiceprintAdapter | None = None,
        diarization_adapter: _DummyDiarizationAdapter | None = None,
    ) -> None:
        self.voiceprint_adapter = voiceprint_adapter or _DummyVoiceprintAdapter()
        self.diarization_adapter = diarization_adapter or _DummyDiarizationAdapter()

    def require_available(self, model_key: str) -> None:
        return None

    def get_asr(self, model_key: str) -> _DummyAsrAdapter:
        return _DummyAsrAdapter()

    def get_diarization(self, model_key: str) -> _DummyDiarizationAdapter:
        return self.diarization_adapter

    def get_voiceprint(self, model_key: str) -> _DummyVoiceprintAdapter:
        return self.voiceprint_adapter


def test_run_multi_speaker_transcription_attaches_timeline_metadata(monkeypatch) -> None:
    monkeypatch.setattr(multi_speaker, "get_worker_registry", lambda: _DummyRegistry())
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(
        multi_speaker,
        "_adapter_asset",
        lambda asset_name: AudioAsset(path=asset_name),
    )

    result = multi_speaker.run_multi_speaker_transcription(job_id="job-1", asset_name="demo.wav")

    assert result.metadata is not None
    assert result.metadata.alignment_source == "exclusive"
    assert result.metadata.diarization_model == "3dspeaker-diarization"
    assert len(result.metadata.timelines) == 3
    assert result.metadata.timelines[0].source == "regular"
    assert result.metadata.timelines[1].source == "exclusive"
    assert result.metadata.timelines[2].source == "display"


def test_run_multi_speaker_transcription_uses_adapter_regular_and_exclusive_timelines(
    monkeypatch,
) -> None:
    registry = _DummyRegistry(diarization_adapter=_DummyDiarizationAdapterWithLastOutputs())
    monkeypatch.setattr(multi_speaker, "get_worker_registry", lambda: registry)
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(
        multi_speaker,
        "_adapter_asset",
        lambda asset_name: AudioAsset(path=asset_name),
    )

    result = multi_speaker.run_multi_speaker_transcription(job_id="job-1", asset_name="demo.wav")

    assert result.metadata is not None
    timelines = {timeline.source: timeline.segments for timeline in result.metadata.timelines}
    assert [(item.start_ms, item.end_ms) for item in timelines["regular"]] == [
        (0, 2500),
        (1500, 4000),
    ]
    assert [(item.start_ms, item.end_ms) for item in timelines["exclusive"]] == [
        (0, 2000),
        (2000, 4000),
    ]


def test_parallel_asr_diarization_auto_requires_enough_free_gpu_memory(monkeypatch) -> None:
    monkeypatch.setattr(multi_speaker, "PARALLEL_ASR_DIARIZATION", "auto")
    monkeypatch.setattr(multi_speaker, "MIN_PARALLEL_FREE_GPU_MB", 10000)
    monkeypatch.setattr(multi_speaker, "_cuda_free_memory_mb", lambda: 8192)

    assert multi_speaker._should_parallelize_asr_diarization() is False

    monkeypatch.setattr(multi_speaker, "_cuda_free_memory_mb", lambda: 12288)

    assert multi_speaker._should_parallelize_asr_diarization() is True


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
    monkeypatch.setattr(
        multi_speaker,
        "_adapter_asset",
        lambda asset_name: AudioAsset(path=asset_name),
    )
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


def test_run_multi_speaker_transcription_uses_explicit_voiceprint_profile_ids(
    monkeypatch,
) -> None:
    from apps.api.app.services import job_db

    selected_profile_id = "unit-profile-explicit-selected"
    ignored_profile_id = "unit-profile-explicit-ignored"
    with job_db.session() as db:
        db.merge(
            job_db.VoiceprintProfileRecord(
                profile_id=selected_profile_id,
                display_name="指定候选人",
                model_key="3dspeaker-embedding",
                sample_count=1,
            )
        )
        db.merge(
            job_db.VoiceprintProfileRecord(
                profile_id=ignored_profile_id,
                display_name="不应进入候选",
                model_key="3dspeaker-embedding",
                sample_count=1,
            )
        )
        db.commit()

    voiceprint_adapter = _DummyVoiceprintAdapter()
    monkeypatch.setattr(
        multi_speaker,
        "get_worker_registry",
        lambda: _DummyRegistry(voiceprint_adapter),
    )
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(
        multi_speaker,
        "_adapter_asset",
        lambda asset_name: AudioAsset(path=asset_name),
    )
    monkeypatch.setattr(
        multi_speaker,
        "_build_speaker_probe_assets",
        lambda asset, segments, speakers, tmpdir: [
            (speaker, AudioAsset(path=f"{speaker}.wav"))
            for speaker in speakers
        ],
    )

    result = multi_speaker.run_multi_speaker_transcription(
        job_id="job-voiceprint-explicit",
        asset_name="demo.wav",
        voiceprint_profile_ids=[selected_profile_id],
    )

    assert result.metadata is not None
    assert result.metadata.voiceprint_matches
    assert result.metadata.voiceprint_matches[0].scope_mode == "none"
    assert result.metadata.voiceprint_matches[0].candidate_profile_ids == [selected_profile_id]
    assert result.metadata.voiceprint_matches[0].candidates[0].profile_id == selected_profile_id
    assert voiceprint_adapter.seen_profile_ids
    assert all(
        profile_ids == [selected_profile_id]
        for profile_ids in voiceprint_adapter.seen_profile_ids
    )


def test_build_speaker_probe_assets_prefers_clean_high_energy_segments(tmp_path) -> None:
    import numpy as np
    import soundfile as sf

    sample_rate = 16000
    audio = np.zeros(sample_rate * 5, dtype=np.float32)
    audio[0:sample_rate] = 0.02
    audio[sample_rate:sample_rate * 3] = 0.6
    audio[sample_rate * 3:sample_rate * 5] = 0.4
    source = tmp_path / "source.wav"
    sf.write(source, audio, sample_rate)

    built = multi_speaker._build_speaker_probe_assets(
        AudioAsset(path=str(source), sample_rate=sample_rate, channels=1),
        [
            Segment(start_ms=0, end_ms=1000, speaker="SPEAKER_00", confidence=0.95),
            Segment(start_ms=1000, end_ms=3000, speaker="SPEAKER_00", confidence=0.95),
            Segment(start_ms=1500, end_ms=2800, speaker="SPEAKER_01", confidence=0.95),
            Segment(start_ms=3000, end_ms=5000, speaker="SPEAKER_00", confidence=0.95),
        ],
        ["SPEAKER_00"],
        tmp_path,
    )

    assert len(built) == 1
    probe_audio, probe_rate = sf.read(built[0][1].path, dtype="float32")
    assert probe_rate == sample_rate
    assert 1.9 <= len(probe_audio) / sample_rate <= 2.1
    assert float(np.mean(np.abs(probe_audio))) > 0.3
