from __future__ import annotations

from ..api.schemas import MeetingMinutesLLMInfo
from ..core.config import Settings, get_settings


def get_meeting_minutes_llm_info(settings: Settings | None = None) -> MeetingMinutesLLMInfo:
    current = settings or get_settings()
    api_key_configured = bool((current.minutes_llm_api_key or "").strip())
    base_url = current.minutes_llm_base_url.rstrip("/")
    warning = None
    if not api_key_configured:
        warning = (
            "未配置会议纪要 LLM API Key；"
            "use_llm=true 时不可调用模型，将仅能使用本地规则纪要。"
        )
    elif not base_url:
        warning = "未配置会议纪要 LLM Base URL。"

    return MeetingMinutesLLMInfo(
        configured=api_key_configured and bool(base_url),
        model=current.minutes_llm_model,
        base_url=base_url,
        reasoning_split=current.minutes_llm_reasoning_split,
        timeout_seconds=current.minutes_llm_timeout_seconds,
        warning=warning,
    )
