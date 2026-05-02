"""任务服务。

提供任务的创建、查询和管理功能。
支持同步和异步两种执行模式：
- 异步模式：任务提交到 Celery 队列，由 Worker 异步执行
- 同步模式：API 直接执行任务（Redis 不可用时的回退行为）
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from domain.schemas.transcript import JobDetail, JobSummary, Segment, TranscriptResult

from apps.worker.app.celery_app import (
    broker_available,
    broker_error,
    is_async_available,
    worker_available,
    worker_error,
)
from apps.worker.app.tasks.multi_speaker import (
    run_multi_speaker_transcription,
    run_multi_speaker_transcription_task,
)
from apps.worker.app.tasks.transcription import run_transcription, run_transcription_task

from . import job_db
from .asset_storage import asset_storage_service

logger = logging.getLogger(__name__)

CANCELABLE_JOB_STATUSES = {"pending", "queued", "running"}
RETRYABLE_JOB_STATUSES = {"failed", "canceled"}


class JobRetryError(RuntimeError):
    """Raised when a job cannot be retried safely."""


def _sync_transcription_fallback_enabled() -> bool:
    return os.environ.get("ALLOW_SYNC_TRANSCRIPTION_FALLBACK", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_transcription_request_payload(
    *,
    asset_name: str,
    job_type: str,
    asr_model: str,
    diarization_model: str | None,
    hotwords: list[str] | None,
    language: str,
    vad_enabled: bool,
    itn: bool,
    voiceprint_scope_mode: str,
    voiceprint_group_id: str | None,
    voiceprint_profile_ids: list[str] | None,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> dict[str, object]:
    return {
        "asset_name": asset_name,
        "job_type": job_type,
        "asr_model": asr_model,
        "diarization_model": diarization_model,
        "hotwords": hotwords,
        "language": language,
        "vad_enabled": vad_enabled,
        "itn": itn,
        "voiceprint_scope_mode": voiceprint_scope_mode,
        "voiceprint_group_id": voiceprint_group_id,
        "voiceprint_profile_ids": voiceprint_profile_ids,
        "num_speakers": num_speakers,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
    }


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
                normalized_keyword = keyword.lower()
                records = (
                    query.order_by(job_db.JobRecord.created_at.desc())
                    .all()
                )
                filtered_records = [
                    record
                    for record in records
                    if _job_record_matches_keyword(record, normalized_keyword)
                ]
                total = len(filtered_records)
                page_records = filtered_records[(page - 1) * page_size: page * page_size]
                details = [
                    self._with_asset_metadata(
                        self._with_status_explanation(record.to_job_detail())
                    )
                    for record in page_records
                ]
                return [d for d in details if d is not None], total

            total = query.count()
            records = (
                query.order_by(job_db.JobRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            details = [
                self._with_asset_metadata(self._with_status_explanation(record.to_job_detail()))
                for record in records
            ]
            return [d for d in details if d is not None], total

    def get_job(self, job_id: str) -> JobDetail | None:
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            detail = self._with_status_explanation(record.to_job_detail()) if record else None
            return self._with_asset_metadata(detail)

    def delete_job(self, job_id: str) -> bool:
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            if record is None:
                return False
            db.delete(record)
            db.commit()
            return True

    def cancel_job(self, job_id: str) -> JobDetail | None:
        """将可取消任务标记为 canceled。

        取消是轻量语义：不强杀已经进入模型推理的 Worker，但会阻止 Worker 在开始前
        或收尾写结果时把任务覆盖为 succeeded/failed。
        """
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            if record is None:
                return None
            if record.status not in CANCELABLE_JOB_STATUSES:
                return self._with_status_explanation(record.to_job_detail())

            record.status = "canceled"
            record.error_message = "用户取消任务"
            record.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(record)
            return self._with_status_explanation(record.to_job_detail())

    def retry_job(self, job_id: str) -> JobDetail | None:
        """基于原始创建参数重新创建一个转写任务。"""
        with job_db.session() as db:
            record = db.get(job_db.JobRecord, job_id)
            if record is None:
                return None
            if record.status not in RETRYABLE_JOB_STATUSES:
                raise JobRetryError(f"任务当前状态为 {record.status}，仅失败或已取消任务可重试")
            if record.job_type not in job_db.TRANSCRIPTION_JOB_TYPES:
                raise JobRetryError("当前仅转写任务支持重试")
            if not record.request_payload:
                raise JobRetryError("历史任务缺少创建参数，无法安全重试")
            try:
                payload = json.loads(record.request_payload)
            except json.JSONDecodeError as exc:
                raise JobRetryError("历史任务创建参数已损坏，无法安全重试") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("asset_name"), str):
            raise JobRetryError("历史任务创建参数不完整，无法安全重试")

        job_type = payload.get("job_type", "transcription")
        if job_type not in job_db.TRANSCRIPTION_JOB_TYPES:
            raise JobRetryError("历史任务类型不支持重试")

        return self.create_transcription_job(
            asset_name=payload["asset_name"],
            job_type=cast(str, job_type),
            asr_model=cast(str, payload.get("asr_model") or "funasr-nano"),
            diarization_model=cast(str | None, payload.get("diarization_model")),
            hotwords=cast(list[str] | None, payload.get("hotwords")),
            language=cast(str, payload.get("language") or "zh-cn"),
            vad_enabled=bool(payload.get("vad_enabled", True)),
            itn=bool(payload.get("itn", True)),
            voiceprint_scope_mode=cast(str, payload.get("voiceprint_scope_mode") or "none"),
            voiceprint_group_id=cast(str | None, payload.get("voiceprint_group_id")),
            voiceprint_profile_ids=cast(list[str] | None, payload.get("voiceprint_profile_ids")),
            num_speakers=cast(int | None, payload.get("num_speakers")),
            min_speakers=cast(int | None, payload.get("min_speakers")),
            max_speakers=cast(int | None, payload.get("max_speakers")),
        )

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
        request_payload = _build_transcription_request_payload(
            asset_name=asset_name,
            job_type=job_type,
            asr_model=asr_model,
            diarization_model=diarization_model,
            hotwords=hotwords,
            language=language,
            vad_enabled=vad_enabled,
            itn=itn,
            voiceprint_scope_mode=voiceprint_scope_mode,
            voiceprint_group_id=voiceprint_group_id,
            voiceprint_profile_ids=voiceprint_profile_ids,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

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
                request_payload=json.dumps(request_payload, ensure_ascii=False),
                result=None,
                error_message=None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            db.add(record)
            db.commit()

        # 检查是否启用异步模式
        async_available = is_async_available(refresh=True)

        async_submit_error: str | None = None
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
                async_submit_error = str(e)
                logger.warning(f"异步提交失败，回退到同步执行: {e}")
                # 根据配置决定是否允许回退同步执行

        if not async_available or async_submit_error:
            reason = (
                async_submit_error
                or worker_error()
                or broker_error()
                or "async_queue_unavailable"
            )
            if not _sync_transcription_fallback_enabled():
                message = (
                    "异步任务队列不可用，已拒绝在 API 请求线程中同步执行大模型任务。"
                    "请启动 Redis/Celery Worker，或仅在本地调试时设置 "
                    "ALLOW_SYNC_TRANSCRIPTION_FALLBACK=1。"
                    f"原因：{reason}"
                )
                self._update_job_result(job_id, status="failed", error_message=message)
                raise RuntimeError(message)

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
                    if record.status == "canceled" and status != "canceled":
                        logger.info(f"任务 {job_id} 已取消，忽略状态更新: {status}")
                        return False
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
                    if record.status == "canceled" and status != "canceled":
                        logger.info(f"任务 {job_id} 已取消，忽略结果更新: status={status}")
                        return False
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

    def _with_status_explanation(self, job: JobDetail | None) -> JobDetail | None:
        if job is None:
            return None
        return job.model_copy(update={"status_explanation": explain_job_status(job)})

    def _with_asset_metadata(self, job: JobDetail | None) -> JobDetail | None:
        if job is None:
            return None
        original_filename = asset_storage_service.get_original_filename(job.asset_name)
        if not original_filename:
            return job
        return job.model_copy(update={"original_filename": original_filename})


job_service = JobService()


def _job_record_matches_keyword(record: job_db.JobRecord, normalized_keyword: str) -> bool:
    original_filename = asset_storage_service.get_original_filename(record.asset_name)
    candidates = [
        record.asset_name,
        record.job_id,
        original_filename,
    ]
    return any(
        normalized_keyword in str(candidate).lower()
        for candidate in candidates
        if candidate
    )


def explain_job_status(job: JobDetail) -> str | None:
    if job.status == "queued":
        broker_ready = broker_available(refresh=False)
        worker_ready = worker_available(refresh=False)
        if not broker_ready:
            return (
                "任务仍在排队；当前 broker 不可用，系统会在创建新任务时回退同步模式。"
                f"{broker_error() or ''}"
            ).strip()
        if not worker_ready:
            return f"任务仍在排队；Redis 可用但未检测到在线 Worker。{worker_error() or ''}".strip()
        return "任务已进入异步队列，等待 Worker 消费。"
    if job.status == "running":
        worker_ready = worker_available(refresh=False)
        if not worker_ready:
            return f"任务标记为运行中，但当前未检测到在线 Worker。{worker_error() or ''}".strip()
        return "任务正在执行，模型推理或音频处理可能需要较长时间。"
    if job.status == "failed":
        return _explain_failure(job.error_message)
    if job.status == "succeeded":
        return "任务已完成。"
    if job.status == "canceled":
        return (
            "任务已取消；若 Worker 已开始模型推理，本次取消不会强杀进程，"
            "但后续结果不会覆盖取消状态。"
        )
    return None


def _explain_failure(error_message: str | None) -> str:
    if not error_message:
        return "任务失败，但未记录错误详情。"
    lowered = error_message.lower()
    if "cuda" in lowered or "gpu" in lowered:
        return f"任务失败：CUDA/GPU 运行时不可用或显存不足。原始错误：{error_message}"
    if "ffmpeg" in lowered or "decode" in lowered or "解码" in error_message:
        return (
            "任务失败：音频解码失败，请检查 ffmpeg 或先转为 16k mono wav。"
            f"原始错误：{error_message}"
        )
    if "model" in lowered or "模型" in error_message or "unavailable" in lowered:
        return f"任务失败：模型不可用或本地权重不完整。原始错误：{error_message}"
    if "minutes" in lowered or "纪要" in error_message or "llm" in lowered:
        return f"任务失败：会议纪要生成失败或 LLM 配置不可用。原始错误：{error_message}"
    return f"任务失败：{error_message}"
