from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from domain.schemas.transcript import JobDetail, JobSummary, TranscriptResult

TRANSCRIPTION_JOB_TYPES = {"transcription", "multi_speaker_transcription"}


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    asset_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
    )

    def to_job_detail(self) -> JobDetail:
        result_obj: TranscriptResult | None = None
        if self.result and self.job_type in TRANSCRIPTION_JOB_TYPES:
            try:
                result_obj = TranscriptResult.model_validate_json(self.result)
            except Exception:
                result_obj = None
        return JobDetail(
            job_id=self.job_id,
            job_type=self.job_type,  # type: ignore[arg-type]
            status=self.status,  # type: ignore[arg-type]
            asset_name=self.asset_name,
            result=result_obj,
            error_message=self.error_message,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_job_summary(self) -> JobSummary:
        return JobSummary(
            job_id=self.job_id,
            job_type=self.job_type,  # type: ignore[arg-type]
            status=self.status,  # type: ignore[arg-type]
            asset_name=self.asset_name,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class MinutesRecord(Base):
    __tablename__ = "meeting_minutes"

    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.job_id"), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def _storage_path() -> Path:
    return Path(__file__).resolve().parents[4] / "storage"


_engine = None
_SessionFactory: type[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        db_path = _storage_path() / "jobs.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        from sqlalchemy import create_engine
        _engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(_engine)
    return _engine


def get_session_factory() -> type[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory  # type: ignore[return-value]


def session() -> Session:
    return get_session_factory()()
