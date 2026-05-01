"""任务服务。

提供任务的创建、查询和管理功能。
支持同步和异步两种执行模式：
- 异步模式：任务提交到 Celery 队列，由 Worker 异步执行
- 同步模式：API 直接执行任务（Redis 不可用时的回退行为）
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from domain.schemas.transcript import JobDetail, JobSummary, Segment, TranscriptResult

from apps.worker.app.celery_app import is_async_available
from apps.worker.app.tasks.multi_speaker import (
    run_multi_speaker_transcription,
    run_multi_speaker_transcription_task,
)
from apps.worker.app.tasks.transcription import run_transcription, run_transcription_task

from . import job_db

logger = logging.getLogger(__name__)


def _init_demo_job() -> None:
    """在数据库中创建一个演示任务（仅当表为空时）"""
    with job_db.session() as db:
        count = db.query(job_db.JobRecord).count()
        if count == 0:
            demo = job_db.JobRecord(
                job_id=str(uuid4()),
                job_type="transcription",
                status="succeeded",
                asset_name="sample-meeting.wav",
                result=TranscriptResult(
                    text="欢迎使用 voiceprint-asr-platform。",
                    language="zh",
                    segments=[
                        Segment(start_ms=0, end_ms=2300, text="欢迎使用", speaker="SPEAKER_00"),
                        Segment(
                            start_ms=2300,
                            end_ms=5200,
                            text="voiceprint-asr-platform。",
                            speaker="SPEAKER_00",
                        ),
                    ],
                ).model_dump_json(),
                error_message=None,
            )
            db.add(demo)
            db.commit()


# Ensure demo job exists on module load (creates DB + table on first access)
_init_demo_job()


class JobService:
    def list_jobs(self) -> list[JobSummary]:
        with job_db.session() as db:
            return [
                r.to_job_summary()
                for r in db.query(job_db.JobRecord)
                .order_by(job_db.JobRecord.created_at.desc())
                .all()
            ]

    def list_job_details(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        job_type: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[JobDetail], int]:
        with job_db.session() as db:
            query = db.query(job_db.JobRecord)
            if status:
                query = query.filter(job_db.JobRecord.status == status)
            if job_type:
                query = query.filter(job_db.JobRecord.job_type == job_type)
            if keyword:
                like_keyword = f"%{keyword}%"
                query = query.filter(
                    (job_db.JobRecord.asset_name.like(like_keyword))
                    | (job_db.JobRecord.job_id.like(like_keyword))
                )

            total = query.count()
            records = (
                query.order_by(job_db.JobRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            details = [record.to_job_detail() for record in records]
            return [d for d in details if d is not None], total

    def get_job(self, job_id: str) -> JobDetail | None:
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            return record.to_job_detail() if record else None

    def delete_job(self, job_id: str) -> bool:
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            if record is None:
                return False
            db.delete(record)
            db.commit()
            return True

    def create_transcription_job(
        self,
        asset_name: str,
        job_type: str = "transcription",
        *,
        asr_model: str = "funasr-nano",
        diarization_model: str | None = None,
        hotwords: list[str] | None = None,
        language: str = "zh-cn",
        vad_enabled: bool = True,
        itn: bool = True,
        voiceprint_scope_mode: str = "none",
        voiceprint_group_id: str | None = None,
        voiceprint_profile_ids: list[str] | None = None,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> JobDetail:
        """创建转写任务。

        根据配置自动选择同步或异步执行：
        - 异步模式：任务状态为 queued，推送到 Celery 队列
        - 同步模式：直接执行转写，任务状态为 succeeded/failed

        Args:
            asset_name: 音频资产名称
            job_type: 任务类型 (transcription / multi_speaker_transcription)
            diarization_model: 说话人分离模型
            hotwords: 热词列表
            language: 语言
            vad_enabled: 是否启用 VAD
            itn: 是否启用 ITN
            num_speakers: 已知说话人数量
            min_speakers: 最少说话人数量
            max_speakers: 最多说话人数量

        Returns:
            JobDetail 任务详情

        Raises:
            RuntimeError: 当资产不可用时
        """
        job_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # 先创建任务记录（状态为 queued）
        job = JobDetail(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            asset_name=asset_name,
            result=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )

        # 保存到数据库
        with job_db.session() as db:
            record = job_db.JobRecord(
                job_id=job.job_id,
                job_type=job.job_type,
                status=job.status,
                asset_name=job.asset_name,
                result=None,
                error_message=None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            db.add(record)
            db.commit()

        # 检查是否启用异步模式
        async_available = is_async_available(refresh=True)

        if async_available:
            # 异步模式：推送到 Celery 队列
            try:
                if job_type == "transcription":
                    # run_transcription_task 在 celery 可用时是 Celery task 对象，否则是同步 wrapper
                    run_transcription_task.apply_async(
                        args=[job_id, asset_name, asr_model],
                        kwargs={
                            "hotwords": hotwords,
                            "language": language,
                            "vad_enabled": vad_enabled,
                            "itn": itn,
                        },
                    )
                    logger.info(f"任务 {job_id} 已提交到队列（转写）")
                elif job_type == "multi_speaker_transcription":
                    run_multi_speaker_transcription_task.apply_async(
                        args=[
                            job_id,
                            asset_name,
                            asr_model,
                            diarization_model or "3dspeaker-diarization",
                        ],
                        kwargs={
                            "hotwords": hotwords,
                            "language": language,
                            "vad_enabled": vad_enabled,
                            "itn": itn,
                            "num_speakers": num_speakers,
                            "min_speakers": min_speakers,
                            "max_speakers": max_speakers,
                            "voiceprint_scope_mode": voiceprint_scope_mode,
                            "voiceprint_group_id": voiceprint_group_id,
                            "voiceprint_profile_ids": voiceprint_profile_ids,
                        },
                    )
                    logger.info(f"任务 {job_id} 已提交到队列（多人转写）")

                # 返回 queued 状态的任务
                return job

            except Exception as e:
                logger.warning(f"异步提交失败，回退到同步执行: {e}")
                # 回退到同步执行

        # 同步模式：直接执行任务
        logger.info(f"任务 {job_id} 同步执行")
        return self._execute_transcription_sync(
            job_id=job_id,
            asset_name=asset_name,
            job_type=job_type,
            asr_model=asr_model,
            diarization_model=diarization_model,
            hotwords=hotwords,
            language=language,
            vad_enabled=vad_enabled,
            itn=itn,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            voiceprint_scope_mode=voiceprint_scope_mode,
            voiceprint_group_id=voiceprint_group_id,
            voiceprint_profile_ids=voiceprint_profile_ids,
        )

    def _execute_transcription_sync(
        self,
        job_id: str,
        asset_name: str,
        job_type: str,
        asr_model: str = "funasr-nano",
        diarization_model: str | None = None,
        hotwords: list[str] | None = None,
        language: str = "zh-cn",
        vad_enabled: bool = True,
        itn: bool = True,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        voiceprint_scope_mode: str = "none",
        voiceprint_group_id: str | None = None,
        voiceprint_profile_ids: list[str] | None = None,
    ) -> JobDetail:
        """同步执行转写任务（回退模式）。

        内部调用转写函数，更新任务状态为 succeeded/failed。
        """
        result: TranscriptResult | None = None
        error_message: str | None = None

        try:
            # 更新状态为 running
            self._update_job_status(job_id, "running")

            if job_type == "transcription":
                result = run_transcription(
                    job_id=job_id,
                    asset_name=asset_name,
                    model_key=asr_model,
                    hotwords=hotwords,
                    language=language,
                    vad_enabled=vad_enabled,
                    itn=itn,
                )
            elif job_type == "multi_speaker_transcription":
                result = run_multi_speaker_transcription(
                    job_id=job_id,
                    asset_name=asset_name,
                    asr_model_key=asr_model,
                    diarization_model_key=diarization_model or "3dspeaker-diarization",
                    hotwords=hotwords,
                    language=language,
                    vad_enabled=vad_enabled,
                    itn=itn,
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                    voiceprint_scope_mode=voiceprint_scope_mode,
                    voiceprint_group_id=voiceprint_group_id,
                    voiceprint_profile_ids=voiceprint_profile_ids,
                )
        except RuntimeError:
            raise
        except Exception as exc:
            error_message = str(exc)
            logger.error(f"任务 {job_id} 执行失败: {exc}")

        # 更新任务状态
        self._update_job_result(
            job_id,
            result=result,
            status="succeeded" if result is not None else "failed",
            error_message=error_message,
        )

        # 获取更新后的任务
        return self.get_job(job_id) or JobDetail(
            job_id=job_id,
            job_type=job_type,
            status="succeeded" if result is not None else "failed",
            asset_name=asset_name,
            result=result,
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def _update_job_status(self, job_id: str, status: str) -> bool:
        """更新任务状态。"""
        try:
            with job_db.session() as db:
                record = db.get(job_db.JobRecord, job_id)
                if record:
                    record.status = status
                    record.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.debug(f"任务 {job_id} 状态更新为: {status}")
                    return True
            return False
        except Exception as e:
            logger.error(f"更新任务状态失败: {e}")
            return False

    def _update_job_result(
        self,
        job_id: str,
        result: TranscriptResult | None = None,
        status: str = "succeeded",
        error_message: str | None = None,
    ) -> bool:
        """更新任务结果。"""
        try:
            with job_db.session() as db:
                record = db.get(job_db.JobRecord, job_id)
                if record:
                    record.status = status
                    record.updated_at = datetime.now(timezone.utc)
                    if error_message is not None:
                        record.error_message = error_message
                    if result is not None:
                        record.result = result.model_dump_json()
                    db.commit()
                    logger.debug(f"任务 {job_id} 结果已更新: status={status}")
                    return True
            return False
        except Exception as e:
            logger.error(f"更新任务结果失败: {e}")
            return False

    def update_job_status(self, job_id: str, status: str) -> bool:
        """公开方法：更新任务状态。"""
        return self._update_job_status(job_id, status)

    def update_job_result(
        self,
        job_id: str,
        result: TranscriptResult | None = None,
        status: str = "succeeded",
        error_message: str | None = None,
    ) -> bool:
        """公开方法：更新任务结果。"""
        return self._update_job_result(job_id, result, status, error_message)

    def seed_jobs(self, jobs: Iterable[JobDetail]) -> None:
        with job_db.session() as db:
            for job in jobs:
                record = job_db.JobRecord(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    asset_name=job.asset_name,
                    result=job.result.model_dump_json() if job.result else None,
                    error_message=job.error_message,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
                db.add(record)
            db.commit()


job_service = JobService()
