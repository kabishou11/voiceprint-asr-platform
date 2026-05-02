from pathlib import Path

from scripts.download_models import default_downloads, model_ready


def test_default_download_specs_match_required_model_layout(tmp_path) -> None:
    downloads = {item.key: item for item in default_downloads(tmp_path)}

    assert downloads["funasr-nano"].default_model_id == "FunAudioLLM/Fun-ASR-Nano-2512"
    assert downloads["funasr-nano"].target_dir == tmp_path / "Fun-ASR-Nano-2512"
    assert "model.pt" in downloads["funasr-nano"].required_files

    assert (
        downloads["fsmn-vad"].default_model_id
        == "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    )
    assert downloads["fsmn-vad"].target_dir == tmp_path / "FSMN-VAD"

    assert (
        downloads["3dspeaker-campplus"].default_model_id
        == "iic/speech_campplus_sv_zh-cn_16k-common"
    )
    assert downloads["3dspeaker-campplus"].target_dir == tmp_path / "3D-Speaker" / "campplus"


def test_model_ready_requires_all_required_files(tmp_path: Path) -> None:
    download = default_downloads(tmp_path)[0]
    download.target_dir.mkdir(parents=True)

    assert model_ready(download) is False

    for file_name in download.required_files:
        (download.target_dir / file_name).write_text("ok", encoding="utf-8")

    assert model_ready(download) is True
