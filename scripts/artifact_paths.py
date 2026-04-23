from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "storage" / "experiments"


def slugify_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "sample"


def ensure_artifact_dir(sample_name: str) -> Path:
    target = ARTIFACT_ROOT / slugify_name(sample_name)
    target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_artifact_path(sample_name: str, filename: str) -> Path:
    return ensure_artifact_dir(sample_name) / filename
