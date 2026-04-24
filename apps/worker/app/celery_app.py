"""Celery 应用配置。

使用 Redis 作为 broker 和 backend。
如果 Redis 不可用，可以配置 ASYNC_MODE=disabled 来禁用异步模式。
"""
from __future__ import annotations

import logging
import os
import time

from celery import Celery

logger = logging.getLogger(__name__)

# Redis DSN 配置
REDIS_DSN = os.getenv("REDIS_DSN", "redis://localhost:6379/0")

# 异步模式控制
ASYNC_MODE = os.getenv("ASYNC_MODE", "auto").lower()  # auto | enabled | disabled


def _create_celery_app() -> Celery | None:
    """创建 Celery app 实例。如果 Redis 不可用则返回 None。"""
    try:
        from apps.api.app.core.config import get_settings
        settings = get_settings()
        redis_dsn = settings.redis_dsn
    except Exception:
        redis_dsn = REDIS_DSN

    app = Celery(
        "voiceprint",
        broker=redis_dsn,
        backend=redis_dsn,
        include=[
            "apps.worker.app.tasks.transcription",
            "apps.worker.app.tasks.multi_speaker",
            "apps.worker.app.tasks.voiceprint",
        ],
    )

    # Celery 配置
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # 结果过期时间（秒）
        result_expires=3600,
        # 任务重试配置
        task_default_retry_delay=60,
        task_max_retries=3,
    )

    return app


# 尝试创建 Celery app
_celery_app: Celery | None = None
_async_mode_available: bool | None = None
_broker_available: bool | None = None
_worker_available: bool | None = None
_broker_checked_at = 0.0
_worker_checked_at = 0.0
_async_checked_at = 0.0
_last_broker_error: str | None = None
_last_worker_error: str | None = None
_last_broker_warning_at = 0.0
_last_worker_warning_at = 0.0
_CHECK_TTL_SECONDS = 15.0
_WARNING_TTL_SECONDS = 60.0


def _cache_valid(checked_at: float) -> bool:
    return checked_at > 0 and time.monotonic() - checked_at < _CHECK_TTL_SECONDS


def _warning_due(checked_at: float) -> bool:
    return checked_at <= 0 or time.monotonic() - checked_at >= _WARNING_TTL_SECONDS


def _get_redis_dsn() -> str:
    try:
        from apps.api.app.core.config import get_settings

        settings = get_settings()
        return settings.redis_dsn
    except Exception:
        return REDIS_DSN


def get_celery_app() -> Celery | None:
    """获取 Celery app 实例。"""
    global _celery_app
    if _celery_app is None:
        _celery_app = _create_celery_app()
    return _celery_app


def is_async_available(*, refresh: bool = False) -> bool:
    """检测异步模式是否可用。

    如果 ASYNC_MODE=disabled，返回 False。
    如果 ASYNC_MODE=enabled，尝试连接 Redis。
    如果 ASYNC_MODE=auto，自动检测 Redis 可用性。
    """
    global _async_mode_available, _async_checked_at

    if _async_mode_available is not None and _cache_valid(_async_checked_at):
        return _async_mode_available

    if ASYNC_MODE == "disabled":
        _async_mode_available = False
        _async_checked_at = time.monotonic()
        return False

    if ASYNC_MODE == "enabled":
        _async_mode_available = broker_available(refresh=refresh) and worker_available(refresh=refresh)
        _async_checked_at = time.monotonic()
        return _async_mode_available

    # auto 模式
    _async_mode_available = broker_available(refresh=refresh) and worker_available(refresh=refresh)
    _async_checked_at = time.monotonic()
    return _async_mode_available


def _check_redis_connection() -> bool:
    """检查 Redis 连接是否可用。"""
    global _last_broker_error, _last_broker_warning_at

    import redis

    try:
        client = redis.Redis.from_url(
            _get_redis_dsn(),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _last_broker_error = None
        logger.info("Redis 连接正常，异步模式已启用")
        return True
    except Exception as e:
        _last_broker_error = str(e)
        if _warning_due(_last_broker_warning_at):
            logger.warning(f"Redis 不可用，异步模式已禁用: {e}")
            _last_broker_warning_at = time.monotonic()
        return False


def broker_available(*, refresh: bool = False) -> bool:
    global _broker_available, _broker_checked_at
    if _broker_available is None or not _cache_valid(_broker_checked_at):
        _broker_available = _check_redis_connection()
        _broker_checked_at = time.monotonic()
    return _broker_available


def _check_worker_connection() -> bool:
    global _last_worker_error, _last_worker_warning_at

    if not broker_available(refresh=True):
        _last_worker_error = "broker_unavailable"
        return False

    try:
        celery_app = get_celery_app()
        if celery_app is None:
            return False
        inspector = celery_app.control.inspect(timeout=1.5)
        response = inspector.ping() if inspector is not None else None
        if response:
            _last_worker_error = None
            logger.info("Celery Worker 在线，异步队列可消费")
            return True
        _last_worker_error = "worker_offline"
        if _warning_due(_last_worker_warning_at):
            logger.warning("Redis 可用，但未检测到在线 Celery Worker，异步模式将回退为同步执行")
            _last_worker_warning_at = time.monotonic()
        return False
    except Exception as e:
        _last_worker_error = str(e)
        if _warning_due(_last_worker_warning_at):
            logger.warning(f"检测 Celery Worker 失败，异步模式将回退为同步执行: {e}")
            _last_worker_warning_at = time.monotonic()
        return False


def worker_available(*, refresh: bool = False) -> bool:
    global _worker_available, _worker_checked_at
    if _worker_available is None or not _cache_valid(_worker_checked_at):
        _worker_available = _check_worker_connection()
        _worker_checked_at = time.monotonic()
    return _worker_available


def broker_error() -> str | None:
    return _last_broker_error


def worker_error() -> str | None:
    return _last_worker_error


def reset_async_mode_check():
    """重置异步模式检查状态（用于测试）。"""
    global _async_mode_available, _celery_app, _broker_available, _worker_available
    global _async_checked_at, _broker_checked_at, _worker_checked_at
    global _last_broker_error, _last_worker_error, _last_broker_warning_at, _last_worker_warning_at
    _async_mode_available = None
    _celery_app = None
    _broker_available = None
    _worker_available = None
    _async_checked_at = 0.0
    _broker_checked_at = 0.0
    _worker_checked_at = 0.0
    _last_broker_error = None
    _last_worker_error = None
    _last_broker_warning_at = 0.0
    _last_worker_warning_at = 0.0
