from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="voiceprint-asr-platform", alias="APP_NAME")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    postgres_dsn: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/voiceprint",
        alias="POSTGRES_DSN",
    )
    redis_dsn: str = Field(default="redis://localhost:6379/0", alias="REDIS_DSN")
    s3_endpoint: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="minioadmin", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="minioadmin", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="voiceprint-assets", alias="S3_BUCKET")
    funasr_model: str = Field(default="models/Fun-ASR-Nano-2512", alias="FUNASR_MODEL")
    three_d_speaker_model: str = Field(
        default="iic/speech_campplus_sv_zh_en_16k-common_advanced",
        alias="THREE_D_SPEAKER_MODEL",
    )
    pyannote_model: str = Field(
        default="pyannote/speaker-diarization-community-1",
        alias="PYANNOTE_MODEL",
    )
    enable_pyannote: bool = Field(default=False, alias="ENABLE_PYANNOTE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
