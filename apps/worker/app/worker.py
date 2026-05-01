"""Worker 启动入口。

使用 Celery 启动 worker 来消费异步任务。

用法:
    # 开发模式（单 worker）
    celery -A apps.worker.app.celery_app worker --loglevel=info

    # 或使用 Python 启动
    python -m apps.worker.app.worker
"""
from __future__ import annotations

import logging
import os
import sys

# 设置路径以支持模块导入
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from apps.worker.app.celery_app import get_celery_app  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def build_worker_main_args() -> list[str]:
    """构建 Celery worker 启动参数。

    Celery 的 prefork/spawn 池在 Windows 上容易因为 billiard semaphore 权限失败。
    本地 Windows 开发默认使用 solo 单进程，Linux/容器仍沿用 Celery 默认池。
    """
    loglevel = os.environ.get("CELERY_WORKER_LOGLEVEL", "info")
    args = ["worker", f"--loglevel={loglevel}"]
    pool = os.environ.get("CELERY_WORKER_POOL")
    concurrency = os.environ.get("CELERY_WORKER_CONCURRENCY")

    if not pool and sys.platform.startswith("win"):
        pool = "solo"
    if pool:
        args.append(f"--pool={pool}")

    if not concurrency and sys.platform.startswith("win"):
        concurrency = "1"
    if concurrency:
        args.append(f"--concurrency={concurrency}")

    return args


def main():
    """启动 Celery worker。"""
    celery_app = get_celery_app()

    if celery_app is None:
        logger.error("Celery 不可用，无法启动 worker。请确保 Redis 服务正在运行。")
        sys.exit(1)

    logger.info("正在启动 Celery Worker...")
    logger.info(f"Broker: {celery_app.conf.broker_url}")
    logger.info("按 Ctrl+C 停止 worker")

    worker_args = build_worker_main_args()
    logger.info("Worker 参数: %s", " ".join(worker_args))

    # 启动 worker（Celery 5.x 使用 worker_main()，不是 start()）
    celery_app.worker_main(worker_args)


if __name__ == "__main__":
    main()
