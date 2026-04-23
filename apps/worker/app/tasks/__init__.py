"""任务模块。

导出所有任务函数和 Celery app。
"""
from ._base import create_job_record, update_job_result, update_job_status
from .multi_speaker import (
    execute_multi_speaker_transcription_task,
    run_multi_speaker_transcription,
    run_multi_speaker_transcription_task,
)
from .transcription import (
    execute_transcription_task,
    run_transcription,
    run_transcription_task,
)
from .voiceprint import (
    enroll_voiceprint,
    enroll_voiceprint_task,
    execute_enroll_voiceprint_task,
    execute_identify_voiceprint_task,
    execute_verify_voiceprint_task,
    identify_voiceprint,
    identify_voiceprint_task,
    verify_voiceprint,
    verify_voiceprint_task,
)

__all__ = [
    # transcription
    "run_transcription",
    "run_transcription_task",
    "execute_transcription_task",
    # multi_speaker
    "run_multi_speaker_transcription",
    "run_multi_speaker_transcription_task",
    "execute_multi_speaker_transcription_task",
    # voiceprint
    "enroll_voiceprint",
    "enroll_voiceprint_task",
    "execute_enroll_voiceprint_task",
    "verify_voiceprint",
    "verify_voiceprint_task",
    "execute_verify_voiceprint_task",
    "identify_voiceprint",
    "identify_voiceprint_task",
    "execute_identify_voiceprint_task",
    # base
    "update_job_status",
    "update_job_result",
    "create_job_record",
]
