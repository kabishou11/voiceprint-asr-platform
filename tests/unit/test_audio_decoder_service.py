from apps.api.app.services import audio_decoder


def test_audio_decoder_prefers_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(audio_decoder.shutil, "which", lambda name: "C:/ffmpeg/bin/ffmpeg.exe")
    monkeypatch.setattr(audio_decoder.importlib.util, "find_spec", lambda name: object())

    result = audio_decoder.get_audio_decoder_info()

    assert result.backend == "ffmpeg"
    assert result.ffmpeg_available is True
    assert result.ffmpeg_path == "C:/ffmpeg/bin/ffmpeg.exe"
    assert result.torchaudio_available is True
    assert result.warning is None


def test_audio_decoder_falls_back_to_torchaudio(monkeypatch) -> None:
    monkeypatch.setattr(audio_decoder.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio_decoder.importlib.util, "find_spec", lambda name: object())

    result = audio_decoder.get_audio_decoder_info()

    assert result.backend == "torchaudio"
    assert result.ffmpeg_available is False
    assert result.torchaudio_available is True
    assert "ffmpeg" in (result.warning or "")


def test_audio_decoder_reports_none_when_no_backend(monkeypatch) -> None:
    monkeypatch.setattr(audio_decoder.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio_decoder.importlib.util, "find_spec", lambda name: None)

    result = audio_decoder.get_audio_decoder_info()

    assert result.backend == "none"
    assert result.ffmpeg_available is False
    assert result.torchaudio_available is False
    assert "不可稳定解码" in (result.warning or "")
