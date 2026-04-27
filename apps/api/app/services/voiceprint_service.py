from __future__ import annotations

import logging
from pathlib import Path
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
                self._do_enroll(profile_id, "声纹-女1.wav", mode="replace")
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
        mode: str = "append",
        source_job_id: str | None = None,
    ) -> tuple[VoiceprintProfile, dict[str, str]]:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError("声纹档案不存在")

        asset = self._build_asset(asset_name)
        if not Path(asset.path).exists():
            raise ValueError("音频资产不存在")

        self._do_enroll(profile_id, asset_name, mode=mode)

        sample_id = f"sample-{uuid4().hex[:8]}"
        with job_db.session() as db:
            db.add(job_db.VoiceprintSampleRecord(
                sample_id=sample_id,
                profile_id=profile_id,
                asset_name=asset_name,
                source_job_id=source_job_id,
            ))
            record = db.get(job_db.VoiceprintProfileRecord, profile_id)
            if record is not None:
                record.sample_count = record.sample_count + 1
            db.commit()

        updated_profile = self.get_profile(profile_id)
        enrollment = {
            "profile_id": profile_id,
            "asset_name": asset_name,
            "status": "enrolled",
            "mode": mode,
        }
        return updated_profile or profile, enrollment

    def _do_enroll(self, profile_id: str, asset_name: str, mode: str = "replace") -> None:
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError("声纹档案不存在")
        registry = get_model_registry()
        registry.require_available(profile.model_key)
        adapter = registry.get_voiceprint(profile.model_key)
        adapter.enroll(asset=self._build_asset(asset_name), profile_id=profile_id)

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
    ) -> VoiceprintIdentificationResult:
        registry = get_model_registry()
        registry.require_available("3dspeaker-embedding")
        asset = self._build_asset(probe_asset_name)
        adapter = registry.get_voiceprint("3dspeaker-embedding")
        identified = adapter.identify(asset=asset, top_k=top_k)
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
