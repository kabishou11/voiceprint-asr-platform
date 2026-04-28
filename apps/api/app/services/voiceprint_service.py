from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
    VoiceprintProfile,
    VoiceprintVerificationResult,
)
from model_adapters import resolve_audio_asset_path

from . import job_db
from .model_runtime import get_model_registry

logger = logging.getLogger(__name__)


class VoiceprintService:
    def _seed_demo_profiles(self) -> None:
        with job_db.session() as db:
            if db.query(job_db.VoiceprintProfileRecord).count() > 0:
                return

        self._ensure_profile("sample-female-1", "女声样本 1", "3dspeaker-embedding")
        self._ensure_profile("demo-user", "演示用户", "3dspeaker-embedding")

        for profile_id in ("sample-female-1", "demo-user"):
            try:
                self.enroll_profile(profile_id, "声纹-女1.wav", mode="replace")
            except Exception:
                pass

    def _ensure_profile(self, profile_id: str, display_name: str, model_key: str) -> None:
        with job_db.session() as db:
            existing = db.get(job_db.VoiceprintProfileRecord, profile_id)
            if existing is None:
                db.add(job_db.VoiceprintProfileRecord(
                    profile_id=profile_id,
                    display_name=display_name,
                    model_key=model_key,
                    sample_count=0,
                ))
                db.commit()

    def list_profiles(self) -> list[VoiceprintProfile]:
        with job_db.session() as db:
            records = db.query(job_db.VoiceprintProfileRecord).order_by(
                job_db.VoiceprintProfileRecord.created_at.desc()
            ).all()
            return [
                VoiceprintProfile(
                    profile_id=r.profile_id,
                    display_name=r.display_name,
                    model_key=r.model_key,
                    sample_count=r.sample_count,
                )
                for r in records
            ]

    def get_profile(self, profile_id: str) -> VoiceprintProfile | None:
        with job_db.session() as db:
            r = db.get(job_db.VoiceprintProfileRecord, profile_id)
            if r is None:
                return None
            return VoiceprintProfile(
                profile_id=r.profile_id,
                display_name=r.display_name,
                model_key=r.model_key,
                sample_count=r.sample_count,
            )

    def create_profile(self, display_name: str, model_key: str) -> VoiceprintProfile:
        profile_id = f"profile-{uuid4().hex[:8]}"
        with job_db.session() as db:
            record = job_db.VoiceprintProfileRecord(
                profile_id=profile_id,
                display_name=display_name,
                model_key=model_key,
                sample_count=0,
            )
            db.add(record)
            db.commit()
        return VoiceprintProfile(
            profile_id=profile_id,
            display_name=display_name,
            model_key=model_key,
            sample_count=0,
        )

    def enroll_profile(
        self,
        profile_id: str,
        asset_name: str,
        mode: str = "replace",
        source_job_id: str | None = None,
    ) -> tuple[VoiceprintProfile, dict[str, object]]:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError("声纹档案不存在")

        asset = self._build_asset(asset_name)
        if not Path(asset.path).exists():
            raise ValueError("音频资产不存在")

        if mode not in {"replace", "append"}:
            raise ValueError("声纹注册模式仅支持 replace 或 append")

        quality = self._inspect_enrollment_audio_quality(asset.path)
        self._do_enroll(profile_id, asset_name, mode=mode)

        sample_id = f"sample-{uuid4().hex[:8]}"
        with job_db.session() as db:
            if mode == "replace":
                db.query(job_db.VoiceprintSampleRecord).filter(
                    job_db.VoiceprintSampleRecord.profile_id == profile_id
                ).delete()
            db.add(job_db.VoiceprintSampleRecord(
                sample_id=sample_id,
                profile_id=profile_id,
                asset_name=asset_name,
                source_job_id=source_job_id,
            ))
            record = db.get(job_db.VoiceprintProfileRecord, profile_id)
            if record is not None:
                record.sample_count = (
                    db.query(job_db.VoiceprintSampleRecord)
                    .filter(job_db.VoiceprintSampleRecord.profile_id == profile_id)
                    .count()
                )
            db.commit()

        updated_profile = self.get_profile(profile_id)
        enrollment = {
            "profile_id": profile_id,
            "asset_name": asset_name,
            "status": "enrolled",
            "mode": mode,
            "quality": quality,
        }
        return updated_profile or profile, enrollment

    def _inspect_enrollment_audio_quality(self, asset_path: str) -> dict[str, Any]:
        try:
            import numpy as np
            import soundfile as sf
        except Exception as exc:
            return {
                "available": False,
                "warnings": [f"无法读取音频质量指标: {exc}"],
            }

        warnings: list[str] = []
        try:
            info = sf.info(asset_path)
            sample_count = 0
            sum_squares = 0.0
            peak = 0.0
            with sf.SoundFile(asset_path) as audio_file:
                for block in audio_file.blocks(blocksize=16000, dtype="float32", always_2d=False):
                    audio = np.asarray(block, dtype=np.float32)
                    if getattr(audio, "ndim", 1) > 1:
                        audio = audio.mean(axis=1)
                    if audio.size <= 0:
                        continue
                    sample_count += int(audio.size)
                    sum_squares += float(np.sum(np.square(audio)))
                    peak = max(peak, float(np.max(np.abs(audio))))
            duration_seconds = float(info.frames) / float(info.samplerate) if info.samplerate else 0.0
            rms = (sum_squares / max(1, sample_count)) ** 0.5
        except Exception as exc:
            return {
                "available": False,
                "warnings": [f"无法读取音频质量指标: {exc}"],
            }

        if duration_seconds < 3.0:
            warnings.append("声纹样本短于 3 秒，建议使用更长的清晰人声。")
        if duration_seconds > 180.0:
            warnings.append("声纹样本超过 3 分钟，建议裁剪为更聚焦的单人片段。")
        if rms < 0.005:
            warnings.append("声纹样本音量过低，可能影响识别稳定性。")
        if peak >= 0.999:
            warnings.append("声纹样本可能存在削波，建议降低录音增益后重新注册。")

        return {
            "available": True,
            "duration_seconds": round(duration_seconds, 3),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "rms": round(float(rms), 6),
            "peak": round(float(peak), 6),
            "warnings": warnings,
            "recommended": not warnings,
        }

    def _do_enroll(self, profile_id: str, asset_name: str, mode: str = "replace") -> None:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError("声纹档案不存在")
        registry = get_model_registry()
        registry.require_available(profile.model_key)
        adapter = registry.get_voiceprint(profile.model_key)
        adapter.enroll(asset=self._build_asset(asset_name), profile_id=profile_id, mode=mode)

    def verify(
        self,
        profile_id: str,
        probe_asset_name: str = "5分钟.wav",
        threshold: float = 0.7,
    ) -> VoiceprintVerificationResult:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError("声纹档案不存在")
        if profile.sample_count <= 0:
            raise ValueError("声纹档案尚未注册样本")
        registry = get_model_registry()
        registry.require_available(profile.model_key)
        asset = self._build_asset(probe_asset_name)
        adapter = registry.get_voiceprint(profile.model_key)
        return adapter.verify(asset=asset, profile_id=profile_id, threshold=threshold)

    def identify(
        self,
        probe_asset_name: str = "5分钟.wav",
        top_k: int = 3,
        profile_ids: list[str] | None = None,
    ) -> VoiceprintIdentificationResult:
        registry = get_model_registry()
        registry.require_available("3dspeaker-embedding")
        asset = self._build_asset(probe_asset_name)
        adapter = registry.get_voiceprint("3dspeaker-embedding")
        identified = adapter.identify(asset=asset, top_k=top_k, profile_ids=profile_ids)
        profile_map = {p.profile_id: p.display_name for p in self.list_profiles()}
        candidates = [
            VoiceprintIdentificationCandidate(
                profile_id=c.profile_id,
                display_name=profile_map.get(c.profile_id, c.display_name),
                score=c.score,
                rank=c.rank,
            )
            for c in identified.candidates
        ]
        return VoiceprintIdentificationResult(candidates=candidates, matched=identified.matched)

    def _build_asset(self, asset_name: str):
        from model_adapters import AudioAsset
        return AudioAsset(path=resolve_audio_asset_path(asset_name))


voiceprint_service = VoiceprintService()
voiceprint_service._seed_demo_profiles()
