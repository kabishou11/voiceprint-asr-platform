"""任务状态更新辅助函数。

提供数据库操作和 Celery 任务结果更新的工具函数。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from domain.schemas.transcript import TranscriptResult

logger = logging.getLogger(__name__)


def is_job_canceled(job_id: str) -> bool:
    """检查任务是否已被用户取消。"""
    try:
        from apps.api.app.services.job_db import JobRecord, session

        with session() as db:
            record = db.get(JobRecord, job_id)
            return bool(record and record.status == "canceled")
    except Exception as e:
        logger.error(f"检查任务 {job_id} 取消状态失败: {e}")
        return False


def update_job_status(job_id: str, status: str) -> bool:
    """更新任务状态。

    Args:
        job_id: 任务 ID
        status: 新状态 (pending, queued, running, succeeded, failed)

    Returns:
        是否更新成功
    """
    try:
        from apps.api.app.services.job_db import JobRecord, session

        with session() as db:
            record = db.get(JobRecord, job_id)
            if record:
                if record.status == "canceled" and status != "canceled":
                    logger.info(f"任务 {job_id} 已取消，忽略状态更新: {status}")
                    return False
                record.status = status
                record.updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"任务 {job_id} 状态更新为: {status}")
                return True
            else:
                logger.warning(f"任务 {job_id} 未找到")
                return False
    except Exception as e:
        logger.error(f"更新任务 {job_id} 状态失败: {e}")
        return False


def update_job_result(
    job_id: str,
    result: TranscriptResult | dict | None = None,
    status: str = "succeeded",
    error_message: str | None = None,
) -> bool:
    """更新任务结果。

    Args:
        job_id: 任务 ID
        result: 转写结果（TranscriptResult 对象或 dict）
        status: 最终状态 (succeeded 或 failed)
        error_message: 错误信息

    Returns:
        是否更新成功
    """
    try:
        from apps.api.app.services.job_db import JobRecord, session

        with session() as db:
            record = db.get(JobRecord, job_id)
            if record:
                if record.status == "canceled" and status != "canceled":
                    logger.info(f"任务 {job_id} 已取消，忽略结果更新: status={status}")
                    return False
                record.status = status
                record.updated_at = datetime.now(timezone.utc)

                if error_message is not None:
                    record.error_message = error_message

                if result is not None:
                    if isinstance(result, TranscriptResult):
                        record.result = result.model_dump_json()
                    elif isinstance(result, dict):
                        record.result = __import__("json").dumps(result)
                    else:
                        record.result = str(result)

                db.commit()
                logger.info(f"任务 {job_id} 结果已更新: status={status}")
                return True
            else:
                logger.warning(f"任务 {job_id} 未找到")
                return False
    except Exception as e:
        logger.error(f"更新任务 {job_id} 结果失败: {e}")
        return False


def create_job_record(
    job_id: str,
    job_type: str,
    asset_name: str | None = None,
    status: str = "queued",
) -> bool:
    """创建任务记录。

    Args:
        job_id: 任务 ID
        job_type: 任务类型 (transcription, multi_speaker_transcription, voiceprint)
        asset_name: 资产名称
        status: 初始状态

    Returns:
        是否创建成功
    """
    try:
        from apps.api.app.services.job_db import JobRecord, session

        with session() as db:
            # 检查是否已存在
            existing = db.get(JobRecord, job_id)
            if existing:
                logger.warning(f"任务 {job_id} 已存在")
                return True

            record = JobRecord(
                job_id=job_id,
                job_type=job_type,
                status=status,
                asset_name=asset_name,
            )
            db.add(record)
            db.commit()
            logger.info(f"任务 {job_id} 已创建: type={job_type}, status={status}")
            return True
    except Exception as e:
        logger.error(f"创建任务 {job_id} 失败: {e}")
        return False
