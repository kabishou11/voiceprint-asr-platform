from __future__ import annotations

from pathlib import Path

from domain.schemas.voiceprint import (
    VoiceprintIdentificationCandidate,
    VoiceprintIdentificationResult,
    VoiceprintProfile,
    VoiceprintVerificationResult,
)
from model_adapters import resolve_audio_asset_path

from .model_runtime import get_model_registry


class VoiceprintService:
    def __init__(self) -> None:
        self._profiles: dict[str, VoiceprintProfile] = {}
        self._seed_demo_profiles()

    def _seed_demo_profiles(self) -> None:
        sample_profile = VoiceprintProfile(
            profile_id="sample-female-1",
            display_name="女声样本 1",
            model_key="3dspeaker-embedding",
        )
        self._profiles[sample_profile.profile_id] = sample_profile
        self._enroll_sample_profile(sample_profile.profile_id, "声纹-女1.wav")

        demo_profile = VoiceprintProfile(
            profile_id="demo-user",
            display_name="演示用户",
            model_key="3dspeaker-embedding",
        )
        self._profiles[demo_profile.profile_id] = demo_profile
        self._enroll_sample_profile(demo_profile.profile_id, "声纹-女1.wav")

    def _enroll_sample_profile(self, profile_id: str, asset_name: str) -> None:
        try:
            registry = get_model_registry()
            registry.require_available("3dspeaker-embedding")
            adapter = registry.get_voiceprint("3dspeaker-embedding")
            adapter.enroll(asset=self._build_asset(asset_name), profile_id=profile_id)
        except Exception:
            # Demo profile seed must never block API startup.
            return
        self._profiles[profile_id] = self._profiles[profile_id].model_copy(update={'sample_count': 1})

    def list_profiles(self) -> list[VoiceprintProfile]:
        return list(self._profiles.values())

    def create_profile(self, display_name: str, model_key: str) -> VoiceprintProfile:
        profile_id = f"profile-{len(self._profiles) + 1}"
        profile = VoiceprintProfile(
            profile_id=profile_id,
            display_name=display_name,
            model_key=model_key,
            sample_count=0,
        )
        self._profiles[profile.profile_id] = profile
        return profile

    def enroll_profile(self, profile_id: str, asset_name: str) -> tuple[VoiceprintProfile, dict[str, str]]:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise KeyError('声纹档案不存在')

        asset = self._build_asset(asset_name)
        if not Path(asset.path).exists():
            raise ValueError('音频资产不存在')

        registry = get_model_registry()
        registry.require_available(profile.model_key)
        adapter = registry.get_voiceprint(profile.model_key)
        adapter.enroll(asset=asset, profile_id=profile_id)
        updated_profile = profile.model_copy(update={'sample_count': 1})
        self._profiles[profile_id] = updated_profile
        enrollment = {
            'profile_id': profile_id,
            'asset_name': asset_name,
            'status': 'enrolled',
            'mode': 'replace',
        }
        return updated_profile, enrollment

    def verify(self, profile_id: str, probe_asset_name: str = "5分钟.wav", threshold: float = 0.7) -> VoiceprintVerificationResult:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise KeyError('声纹档案不存在')
        if profile.sample_count <= 0:
            raise ValueError('声纹档案尚未注册样本')
        registry = get_model_registry()
        registry.require_available(profile.model_key)
        asset = self._build_asset(probe_asset_name)
        adapter = registry.get_voiceprint(profile.model_key)
        return adapter.verify(asset=asset, profile_id=profile_id, threshold=threshold)

    def identify(self, probe_asset_name: str = "5分钟.wav", top_k: int = 3) -> VoiceprintIdentificationResult:
        registry = get_model_registry()
        registry.require_available("3dspeaker-embedding")
        asset = self._build_asset(probe_asset_name)
        adapter = registry.get_voiceprint("3dspeaker-embedding")
        identified = adapter.identify(asset=asset, top_k=top_k)
        profile_map = {profile.profile_id: profile.display_name for profile in self.list_profiles()}
        candidates = [
            VoiceprintIdentificationCandidate(
                profile_id=candidate.profile_id,
                display_name=profile_map.get(candidate.profile_id, candidate.display_name),
                score=candidate.score,
                rank=candidate.rank,
            )
            for candidate in identified.candidates
        ]
        return VoiceprintIdentificationResult(candidates=candidates, matched=identified.matched)

    def _build_asset(self, asset_name: str):
        from model_adapters import AudioAsset

        return AudioAsset(path=resolve_audio_asset_path(asset_name))


voiceprint_service = VoiceprintService()
