from pathlib import Path

from scripts.check_models import build_models_report, main, render_markdown_report


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_build_models_report_marks_core_models_available(tmp_path: Path) -> None:
    _write_core_model_files(tmp_path)

    report = build_models_report(tmp_path)

    assert report["summary"]["all_required_available"] is True
    assert report["summary"]["available_required_count"] == 3
    assert {row["status"] for row in report["models"]} == {"available"}


def test_build_models_report_reports_missing_and_undersized_files(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "Fun-ASR-Nano-2512" / "model.pt", 32)
    _write_bytes(tmp_path / "Fun-ASR-Nano-2512" / "config.yaml", 8)

    report = build_models_report(tmp_path)
    rows = {row["key"]: row for row in report["models"]}

    assert report["summary"]["all_required_available"] is False
    assert rows["funasr-nano"]["status"] == "incomplete"
    assert rows["funasr-nano"]["missing_files"] == ["configuration.json"]
    assert rows["funasr-nano"]["undersized_files"][0]["path"] == "model.pt"
    assert rows["fsmn-vad"]["status"] == "missing"


def test_render_markdown_report_includes_model_status(tmp_path: Path) -> None:
    _write_core_model_files(tmp_path)

    markdown = render_markdown_report(build_models_report(tmp_path))

    assert "# 本地模型完整性检查" in markdown
    assert "FunASR Nano ASR" in markdown
    assert "| 3D-Speaker CAM++ | 是 | available |" in markdown


def test_main_returns_non_zero_when_required_models_are_missing(tmp_path: Path) -> None:
    assert main(["--models-root", str(tmp_path), "--json"]) == 1
    assert main(["--models-root", str(tmp_path), "--json", "--no-fail"]) == 0


def _write_core_model_files(root: Path) -> None:
    _write_bytes(root / "Fun-ASR-Nano-2512" / "model.pt", 1024 * 1024)
    _write_bytes(root / "Fun-ASR-Nano-2512" / "config.yaml", 8)
    _write_bytes(root / "Fun-ASR-Nano-2512" / "configuration.json", 8)
    _write_bytes(root / "FSMN-VAD" / "model.pt", 1024)
    _write_bytes(root / "FSMN-VAD" / "config.yaml", 8)
    _write_bytes(root / "FSMN-VAD" / "configuration.json", 8)
    _write_bytes(root / "3D-Speaker" / "campplus" / "campplus_cn_3dspeaker.bin", 1024 * 1024)
    _write_bytes(root / "3D-Speaker" / "campplus" / "configuration.json", 8)
