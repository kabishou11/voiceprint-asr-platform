from pathlib import Path

from scripts.deployment_preflight import (
    _mask_dsn,
    _three_d_speaker_reference_info,
    render_markdown_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_mask_dsn_hides_password() -> None:
    assert (
        _mask_dsn("postgresql+psycopg://postgres:secret@postgres:5432/voiceprint")
        == "postgresql+psycopg:***@postgres:5432/voiceprint"
    )


def test_render_markdown_report_lists_blockers() -> None:
    markdown = render_markdown_report(
        {
            "python": {"version": "3.13.0"},
            "ffmpeg": {"available": False, "path": None},
            "torch": {"version": None, "cuda_available": False, "device_name": None},
            "models": {
                "summary": {
                    "available_required_count": 0,
                    "required_count": 3,
                }
            },
            "summary": {
                "production_ready": False,
                "ffmpeg_ready": False,
                "storage_ready": False,
                "three_d_speaker_reference_ready": False,
            },
        }
    )

    assert "# 部署前环境自检" in markdown
    assert "生产就绪: False" in markdown
    assert "确认安装 ffmpeg" in markdown
    assert "THREE_D_SPEAKER_REFERENCE_ROOT" in markdown


def test_three_d_speaker_reference_info_prefers_env_path(monkeypatch, tmp_path) -> None:
    reference_root = tmp_path / "3D-Speaker"
    (reference_root / "speakerlab").mkdir(parents=True)
    monkeypatch.setenv("THREE_D_SPEAKER_REFERENCE_ROOT", str(reference_root))

    report = _three_d_speaker_reference_info()

    assert report["available"] is True
    assert report["path"] == str(reference_root)


def test_backend_dockerfiles_keep_cuda_torch_after_project_sync() -> None:
    for dockerfile in [
        PROJECT_ROOT / "apps/api/Dockerfile",
        PROJECT_ROOT / "apps/worker/Dockerfile",
    ]:
        content = dockerfile.read_text(encoding="utf-8")
        cuda_install_index = content.index("--index-url https://download.pytorch.org/whl/cu124")

        assert "torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0" in content
        assert "uv sync --extra asr-funasr --extra speaker-3ds --no-install-project" in content

        later_uv_sync_lines = [
            line.strip()
            for line in content[cuda_install_index:].splitlines()
            if line.strip().startswith("RUN uv sync")
        ]
        assert later_uv_sync_lines
        assert all("--inexact" in line for line in later_uv_sync_lines)
