from scripts.deployment_preflight import _mask_dsn, render_markdown_report


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
            },
        }
    )

    assert "# 部署前环境自检" in markdown
    assert "生产就绪: False" in markdown
    assert "确认安装 ffmpeg" in markdown
