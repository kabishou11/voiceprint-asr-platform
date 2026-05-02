from __future__ import annotations

import json
from pathlib import Path
from secrets import token_hex
from typing import BinaryIO

ALLOWED_SUFFIXES = {'.wav', '.m4a', '.mp3', '.flac'}


class AssetStorageService:
    def __init__(self) -> None:
        self._upload_dir = Path(__file__).resolve().parents[4] / 'storage' / 'uploads'
        self._manifest_path = self._upload_dir / '.assets.json'

    def save_upload(self, filename: str | None, fileobj: BinaryIO) -> dict[str, int | str | None]:
        if not filename:
            raise ValueError('缺少文件名')
        original_name = Path(filename).name
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError('仅支持 wav、m4a、mp3、flac 音频文件')

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        asset_name = f"{token_hex(8)}{suffix}"
        destination = self._upload_dir / asset_name

        size = 0
        with destination.open('wb') as target:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                target.write(chunk)

        if size == 0:
            destination.unlink(missing_ok=True)
            raise ValueError('上传文件为空')

        self._remember_original_filename(asset_name, original_name)

        return {
            'asset_name': asset_name,
            'original_filename': original_name,
            'size': size,
        }

    def get_original_filename(self, asset_name: str | None) -> str | None:
        if not asset_name:
            return None
        return self._read_manifest().get(asset_name)

    def _remember_original_filename(self, asset_name: str, original_name: str) -> None:
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest()
        manifest[asset_name] = original_name
        self._manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    def _read_manifest(self) -> dict[str, str]:
        if not self._manifest_path.is_file():
            return {}
        try:
            payload = json.loads(self._manifest_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if value}


asset_storage_service = AssetStorageService()
