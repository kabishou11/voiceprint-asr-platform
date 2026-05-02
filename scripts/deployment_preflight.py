from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_models import build_models_report  # noqa: E402


def build_preflight_report(*, models_root: str | Path = "models") -> dict[str, Any]:
    torch_info = _torch_info()
    ffmpeg_path = shutil.which("ffmpeg")
    storage_root = Path("storage")
    models_report = build_models_report(models_root)
    three_d_speaker_reference = _three_d_speaker_reference_info()
    return {
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_path),
            "path": ffmpeg_path,
        },
        "torch": torch_info,
        "services": {
            "redis_dsn": _mask_dsn(os.getenv("REDIS_DSN", "redis://localhost:6379/0")),
            "postgres_configured": bool(os.getenv("POSTGRES_DSN")),
            "s3_configured": bool(os.getenv("S3_ENDPOINT")),
        },
        "storage": {
            "path": str(storage_root),
            "writable": _is_writable_dir(storage_root),
        },
        "models": models_report,
        "three_d_speaker_reference": three_d_speaker_reference,
        "summary": {
            "production_ready": bool(
                ffmpeg_path
                and torch_info.get("cuda_available") is True
                and models_report["summary"]["all_required_available"]
                and three_d_speaker_reference["available"]
                and _is_writable_dir(storage_root)
            ),
            "required_models_ready": models_report["summary"]["all_required_available"],
            "three_d_speaker_reference_ready": three_d_speaker_reference["available"],
            "cuda_ready": torch_info.get("cuda_available") is True,
            "ffmpeg_ready": bool(ffmpeg_path),
            "storage_ready": _is_writable_dir(storage_root),
        },
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    torch_info = report["torch"]
    lines = [
        "# 部署前环境自检",
        "",
        f"- 生产就绪: {summary['production_ready']}",
        f"- Python: {report['python']['version']}",
        f"- ffmpeg: {'available' if summary['ffmpeg_ready'] else 'missing'}",
        f"- torch: {torch_info.get('version') or 'missing'}",
        f"- CUDA: {torch_info.get('cuda_available')}",
        f"- GPU: {torch_info.get('device_name') or 'N/A'}",
        f"- 必需模型: {report['models']['summary']['available_required_count']}/"
        f"{report['models']['summary']['required_count']} 可用",
        f"- 3D-Speaker 参考源码: "
        f"{'available' if summary['three_d_speaker_reference_ready'] else 'missing'}",
        f"- storage 可写: {summary['storage_ready']}",
        "",
    ]
    if not summary["production_ready"]:
        lines.extend(
            [
                "## 需要处理",
                "",
                "- 确认安装 ffmpeg，并能在 PATH 中找到。",
                "- 确认安装 CUDA 版 torch/torchaudio，且 torch.cuda.is_available() 为 True。",
                "- 确认 models/ 下 FunASR、FSMN-VAD、3D-Speaker CAM++ 必需文件齐全。",
                "- 确认 THREE_D_SPEAKER_REFERENCE_ROOT 指向包含 speakerlab/ 的 "
                "3D-Speaker 源码目录。",
                "- 确认 storage/ 是持久化目录且 API/Worker 都可读写。",
                "",
            ]
        )
    return "\n".join(lines)


def _torch_info() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"available": False, "cuda_available": False, "version": None}
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        return {
            "available": True,
            "version": getattr(torch, "__version__", None),
            "cuda_runtime": getattr(torch.version, "cuda", None),
            "cuda_available": cuda_available,
            "device_count": int(torch.cuda.device_count()) if cuda_available else 0,
            "device_name": torch.cuda.get_device_name(0) if cuda_available else None,
        }
    except Exception as exc:
        return {
            "available": True,
            "cuda_available": False,
            "error": str(exc),
        }


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _three_d_speaker_reference_info() -> dict[str, Any]:
    env_root = os.getenv("THREE_D_SPEAKER_REFERENCE_ROOT")
    candidates = [
        Path(env_root) if env_root else None,
        Path("/opt/3D-Speaker"),
        PROJECT_ROOT.parent / "3D-Speaker",
        Path("F:/1work/音频识别/3D-Speaker"),
    ]
    checked: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        checked.append(str(candidate))
        if (candidate / "speakerlab").exists():
            return {
                "available": True,
                "path": str(candidate),
                "checked": checked,
            }
    return {
        "available": False,
        "path": None,
        "checked": checked,
    }


def _mask_dsn(value: str) -> str:
    if "@" not in value:
        return value
    prefix, suffix = value.rsplit("@", 1)
    if ":" not in prefix:
        return value
    scheme_user = prefix.split(":", 1)[0]
    return f"{scheme_user}:***@{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="生产部署前环境自检。")
    parser.add_argument("--models-root", default="models")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="未达到 production_ready 时返回 1")
    args = parser.parse_args()

    report = build_preflight_report(models_root=args.models_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(report))
    if args.strict and not report["summary"]["production_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
