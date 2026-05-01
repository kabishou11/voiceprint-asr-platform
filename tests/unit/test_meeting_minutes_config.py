from apps.api.app.core.config import Settings
from apps.api.app.services.meeting_minutes_config import get_meeting_minutes_llm_info


def test_meeting_minutes_llm_info_reports_missing_api_key() -> None:
    settings = Settings(_env_file=None, MINUTES_LLM_API_KEY="")

    info = get_meeting_minutes_llm_info(settings)

    assert info.configured is False
    assert info.model == "MiniMax-M2.7"
    assert info.base_url == "https://api.minimax.chat/v1"
    assert info.warning is not None
    assert "未配置" in info.warning


def test_meeting_minutes_llm_info_reports_configured_backend() -> None:
    settings = Settings(
        _env_file=None,
        MINUTES_LLM_API_KEY="minutes-key",
        MINUTES_LLM_BASE_URL="https://api.example.test/v1/",
        MINUTES_LLM_MODEL="MiniMax-M2.7",
        MINUTES_LLM_REASONING_SPLIT=False,
        MINUTES_LLM_TIMEOUT_SECONDS=45,
    )

    info = get_meeting_minutes_llm_info(settings)

    assert info.configured is True
    assert info.model == "MiniMax-M2.7"
    assert info.base_url == "https://api.example.test/v1"
    assert info.reasoning_split is False
    assert info.timeout_seconds == 45
    assert info.warning is None


def test_meeting_minutes_llm_settings_accept_openai_compatible_aliases() -> None:
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="openai-compatible-key",
        OPENAI_BASE_URL="https://openai-compatible.example.test/v1",
    )

    info = get_meeting_minutes_llm_info(settings)

    assert info.configured is True
    assert info.base_url == "https://openai-compatible.example.test/v1"
