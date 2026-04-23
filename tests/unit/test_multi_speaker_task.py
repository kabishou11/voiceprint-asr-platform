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


class _DummyRegistry:
    def require_available(self, model_key: str) -> None:
        return None

    def get_asr(self, model_key: str) -> _DummyAsrAdapter:
        return _DummyAsrAdapter()

    def get_diarization(self, model_key: str) -> _DummyDiarizationAdapter:
        return _DummyDiarizationAdapter()


def test_run_multi_speaker_transcription_attaches_timeline_metadata(monkeypatch) -> None:
    monkeypatch.setattr(multi_speaker, "get_worker_registry", lambda: _DummyRegistry())
    monkeypatch.setattr(multi_speaker, "preprocess_audio", lambda asset: asset)
    monkeypatch.setattr(multi_speaker, "adapter_asset", lambda asset_name: AudioAsset(path=asset_name))

    result = multi_speaker.run_multi_speaker_transcription(job_id="job-1", asset_name="demo.wav")

    assert result.metadata is not None
    assert result.metadata.alignment_source == "exclusive"
    assert result.metadata.diarization_model == "3dspeaker-diarization"
    assert len(result.metadata.timelines) == 3
    assert result.metadata.timelines[0].source == "regular"
    assert result.metadata.timelines[1].source == "exclusive"
    assert result.metadata.timelines[2].source == "display"
