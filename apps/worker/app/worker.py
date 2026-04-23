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
import sys

# 设置路径以支持模块导入
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from apps.worker.app.celery_app import get_celery_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """启动 Celery worker。"""
    celery_app = get_celery_app()

    if celery_app is None:
        logger.error("Celery 不可用，无法启动 worker。请确保 Redis 服务正在运行。")
        sys.exit(1)

    logger.info("正在启动 Celery Worker...")
    logger.info(f"Broker: {celery_app.conf.broker_url}")
    logger.info("按 Ctrl+C 停止 worker")

    # 启动 worker（Celery 5.x 使用 worker_main()，不是 start()）
    celery_app.worker_main(["worker", "--loglevel=info"])


if __name__ == "__main__":
    main()
