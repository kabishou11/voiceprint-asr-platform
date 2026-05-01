from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RequiredFile:
    path: str
    min_bytes: int = 1


@dataclass(frozen=True)
class ModelCheck:
    key: str
    display_name: str
    directory: str
    required: bool
    files: tuple[RequiredFile, ...]


CORE_MODEL_CHECKS: tuple[ModelCheck, ...] = (
    ModelCheck(
        key="funasr-nano",
        display_name="FunASR Nano ASR",
        directory="Fun-ASR-Nano-2512",
        required=True,
        files=(
            RequiredFile("model.pt", min_bytes=1024 * 1024),
            RequiredFile("config.yaml"),
            RequiredFile("configuration.json"),
        ),
    ),
    ModelCheck(
        key="fsmn-vad",
        display_name="FSMN VAD",
        directory="FSMN-VAD",
        required=True,
        files=(
            RequiredFile("model.pt", min_bytes=1024),
            RequiredFile("config.yaml"),
            RequiredFile("configuration.json"),
        ),
    ),
    ModelCheck(
        key="3dspeaker-campplus",
        display_name="3D-Speaker CAM++",
        directory="3D-Speaker/campplus",
        required=True,
        files=(
            RequiredFile("campplus_cn_3dspeaker.bin", min_bytes=1024 * 1024),
            RequiredFile("configuration.json"),
        ),
    ),
)


def build_models_report(
    models_root: str | Path = "models",
    *,
    include_sha256: bool = False,
) -> dict[str, Any]:
    root = Path(models_root)
    model_rows = [
        _check_model(root, check, include_sha256=include_sha256)
        for check in CORE_MODEL_CHECKS
    ]
    required_rows = [row for row in model_rows if row["required"]]
    available_required_count = sum(1 for row in required_rows if row["available"])
    return {
        "models_root": str(root),
        "summary": {
            "model_count": len(model_rows),
            "required_count": len(required_rows),
            "available_required_count": available_required_count,
            "all_required_available": available_required_count == len(required_rows),
        },
        "models": model_rows,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# 本地模型完整性检查",
        "",
        f"- 模型根目录: {report.get('models_root') or 'models'}",
        f"- 必需模型: {summary.get('available_required_count', 0)}/"
        f"{summary.get('required_count', 0)} 可用",
        f"- 主链路可用: {bool(summary.get('all_required_available'))}",
        "",
        "| 模型 | 必需 | 状态 | 目录 | 缺失/异常文件 | 大小 |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for row in report.get("models") or []:
        issues = []
        issues.extend(row.get("missing_files") or [])
        issues.extend(
            f"{item.get('path')}<{item.get('min_bytes')}B"
            for item in row.get("undersized_files") or []
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("display_name") or row.get("key") or "N/A"),
                    "是" if row.get("required") else "否",
                    str(row.get("status") or "unknown"),
                    str(row.get("path") or "N/A"),
                    ", ".join(issues) if issues else "N/A",
                    _format_bytes(int(row.get("total_size_bytes") or 0)),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _check_model(root: Path, check: ModelCheck, *, include_sha256: bool) -> dict[str, Any]:
    directory = root / Path(check.directory)
    file_rows: list[dict[str, Any]] = []
    missing_files: list[str] = []
    undersized_files: list[dict[str, Any]] = []
    total_size = 0

    for required_file in check.files:
        path = directory / required_file.path
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        total_size += size
        undersized = exists and size < required_file.min_bytes
        if not exists:
            missing_files.append(required_file.path)
        if undersized:
            undersized_files.append(
                {
                    "path": required_file.path,
                    "size_bytes": size,
                    "min_bytes": required_file.min_bytes,
                }
            )
        file_row: dict[str, Any] = {
            "path": required_file.path,
            "exists": exists,
            "size_bytes": size,
            "min_bytes": required_file.min_bytes,
            "mtime": path.stat().st_mtime if exists else None,
        }
        if include_sha256 and exists:
            file_row["sha256"] = _sha256_file(path)
        file_rows.append(file_row)

    available = bool(directory.is_dir()) and not missing_files and not undersized_files
    status = "available" if available else ("missing" if not directory.exists() else "incomplete")
    return {
        "key": check.key,
        "display_name": check.display_name,
        "required": check.required,
        "path": str(directory),
        "available": available,
        "status": status,
        "missing_files": missing_files,
        "undersized_files": undersized_files,
        "total_size_bytes": total_size,
        "files": file_rows,
    }


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查本地核心模型文件是否完整。")
    parser.add_argument("--models-root", default="models", help="模型根目录，默认 models")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    parser.add_argument("--sha256", action="store_true", help="计算关键文件 sha256，适合发布前检查")
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="即使必需模型缺失也返回 0，仅用于展示报告",
    )
    args = parser.parse_args(argv)

    report = build_models_report(args.models_root, include_sha256=args.sha256)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown_report(report), end="")

    if args.no_fail or (report.get("summary") or {}).get("all_required_available"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
