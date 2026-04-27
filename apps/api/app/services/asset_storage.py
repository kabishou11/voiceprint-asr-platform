from __future__ import annotations

from pathlib import Path
from secrets import token_hex
from typing import BinaryIO

MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024
ALLOWED_SUFFIXES = {'.wav', '.m4a', '.mp3', '.flac'}


class AssetStorageService:
    def __init__(self) -> None:
        self._upload_dir = Path(__file__).resolve().parents[4] / 'storage' / 'uploads'

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
                if size > MAX_UPLOAD_SIZE_BYTES:
                    target.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError('上传文件过大，最大支持 100MB')
                target.write(chunk)

        if size == 0:
            destination.unlink(missing_ok=True)
            raise ValueError('上传文件为空')

        return {
            'asset_name': asset_name,
            'original_filename': original_name,
            'size': size,
        }


asset_storage_service = AssetStorageService()
