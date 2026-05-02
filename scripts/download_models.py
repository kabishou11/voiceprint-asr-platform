from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelDownload:
    key: str
    model_id_env: str
    default_model_id: str
    target_dir: Path
    required_files: tuple[str, ...]


DEFAULT_REFERENCE_REPO = "https://github.com/modelscope/3D-Speaker.git"


def default_downloads(models_root: Path) -> tuple[ModelDownload, ...]:
    return (
        ModelDownload(
            key="funasr-nano",
            model_id_env="MODEL_DOWNLOAD_FUNASR_NANO",
            default_model_id="FunAudioLLM/Fun-ASR-Nano-2512",
            target_dir=models_root / "Fun-ASR-Nano-2512",
            required_files=("model.pt", "config.yaml", "configuration.json"),
        ),
        ModelDownload(
            key="fsmn-vad",
            model_id_env="MODEL_DOWNLOAD_FSMN_VAD",
            default_model_id="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            target_dir=models_root / "FSMN-VAD",
            required_files=("model.pt", "config.yaml", "configuration.json"),
        ),
        ModelDownload(
            key="3dspeaker-campplus",
            model_id_env="MODEL_DOWNLOAD_3DSPEAKER_CAMPLUS",
            default_model_id="iic/speech_campplus_sv_zh-cn_16k-common",
            target_dir=models_root / "3D-Speaker" / "campplus",
            required_files=("campplus_cn_3dspeaker.bin", "configuration.json"),
        ),
    )


def model_ready(download: ModelDownload) -> bool:
    return all((download.target_dir / file_name).is_file() for file_name in download.required_files)


def download_model(download: ModelDownload, *, force: bool = False) -> None:
    model_id = os.getenv(download.model_id_env, download.default_model_id).strip()
    if not force and model_ready(download):
        print(f"[models] {download.key} already ready: {download.target_dir}")
        return

    download.target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[models] downloading {download.key}: {model_id} -> {download.target_dir}")

    try:
        from modelscope import snapshot_download
    except Exception as exc:  # pragma: no cover - depends on runtime image
        raise RuntimeError("modelscope is required to download models") from exc

    try:
        snapshot_download(model_id=model_id, local_dir=str(download.target_dir))
    except TypeError:
        cache_dir = snapshot_download(model_id=model_id, cache_dir=str(download.target_dir.parent))
        _copy_tree(Path(cache_dir), download.target_dir)

    if not model_ready(download):
        missing = [
            file_name
            for file_name in download.required_files
            if not (download.target_dir / file_name).is_file()
        ]
        raise RuntimeError(
            f"{download.key} download finished but required files are missing: {missing}"
        )


def ensure_reference_repo(reference_root: Path, *, force: bool = False) -> None:
    if not force and (reference_root / "speakerlab").is_dir():
        print(f"[3D-Speaker] reference runtime already ready: {reference_root}")
        return

    repo_url = os.getenv("THREE_D_SPEAKER_REFERENCE_REPO", DEFAULT_REFERENCE_REPO).strip()
    reference_root.mkdir(parents=True, exist_ok=True)
    if any(reference_root.iterdir()) and not (reference_root / ".git").exists():
        raise RuntimeError(
            f"{reference_root} is not empty and is not a git repository; "
            "set THREE_D_SPEAKER_REFERENCE_ROOT to a clean directory or provide speakerlab/."
        )

    if (reference_root / ".git").exists():
        print(f"[3D-Speaker] updating reference repo: {reference_root}")
        subprocess.run(["git", "-C", str(reference_root), "pull", "--ff-only"], check=True)
    else:
        print(f"[3D-Speaker] cloning reference repo: {repo_url} -> {reference_root}")
        subprocess.run(["git", "clone", "--depth", "1", repo_url, str(reference_root)], check=True)

    if not (reference_root / "speakerlab").is_dir():
        raise RuntimeError(f"3D-Speaker reference repo is missing speakerlab/: {reference_root}")


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download production model artifacts.")
    parser.add_argument("--models-root", default="models")
    parser.add_argument("--reference-root", default=None)
    parser.add_argument("--skip-reference", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    models_root = Path(args.models_root)
    for download in default_downloads(models_root):
        download_model(download, force=args.force)

    if not args.skip_reference:
        reference_root = Path(
            args.reference_root
            or os.getenv("THREE_D_SPEAKER_REFERENCE_ROOT")
            or Path.cwd().parent / "3D-Speaker"
        )
        ensure_reference_repo(reference_root, force=args.force)

    print("[models] all required model assets are ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
