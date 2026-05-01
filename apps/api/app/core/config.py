from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
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
        default="models/3D-Speaker/campplus",
        alias="THREE_D_SPEAKER_MODEL",
    )
    pyannote_model: str = Field(
        default="models/pyannote/speaker-diarization-community-1",
        alias="PYANNOTE_MODEL",
    )
    enable_pyannote: bool = Field(default=False, alias="ENABLE_PYANNOTE")
    enable_3d_speaker_adaptive_clustering: bool = Field(
        default=True,
        alias="ENABLE_3D_SPEAKER_ADAPTIVE_CLUSTERING",
    )
    minutes_llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MINUTES_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    minutes_llm_base_url: str = Field(
        default="https://api.minimax.chat/v1",
        validation_alias=AliasChoices("MINUTES_LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    minutes_llm_model: str = Field(default="MiniMax-M2.7", alias="MINUTES_LLM_MODEL")
    minutes_llm_reasoning_split: bool = Field(default=True, alias="MINUTES_LLM_REASONING_SPLIT")
    minutes_llm_timeout_seconds: float = Field(default=90.0, alias="MINUTES_LLM_TIMEOUT_SECONDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
