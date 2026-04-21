from __future__ import annotations

from dataclasses import dataclass

from model_adapters.base import ASRAdapter, DiarizationAdapter, ModelAvailability, VoiceprintAdapter


@dataclass(slots=True)
class RegistryEntry:
    key: str
    task: str
    adapter: object
    provider: str
    display_name: str
    availability: ModelAvailability = "available"
    experimental: bool = False


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(
        self,
        key: str,
        task: str,
        adapter: object,
        *,
        provider: str,
        display_name: str,
        availability: ModelAvailability = "available",
        experimental: bool = False,
    ) -> None:
        self._entries[key] = RegistryEntry(
            key=key,
            task=task,
            adapter=adapter,
            provider=provider,
            display_name=display_name,
            availability=availability,
            experimental=experimental,
        )

    def get(self, key: str) -> RegistryEntry:
        return self._entries[key]

    def has(self, key: str, task: str | None = None) -> bool:
        entry = self._entries.get(key)
        return entry is not None and (task is None or entry.task == task)

    def get_asr(self, key: str) -> ASRAdapter:
        entry = self._entries[key]
        if not isinstance(entry.adapter, ASRAdapter):
            raise TypeError(f"Model '{key}' is not an ASR adapter")
        return entry.adapter

    def get_diarization(self, key: str) -> DiarizationAdapter:
        entry = self._entries[key]
        if not isinstance(entry.adapter, DiarizationAdapter):
            raise TypeError(f"Model '{key}' is not a diarization adapter")
        return entry.adapter

    def get_voiceprint(self, key: str) -> VoiceprintAdapter:
        entry = self._entries[key]
        if not isinstance(entry.adapter, VoiceprintAdapter):
            raise TypeError(f"Model '{key}' is not a voiceprint adapter")
        return entry.adapter

    def list_entries(self) -> list[RegistryEntry]:
        return list(self._entries.values())


def build_default_registry(
    *,
    funasr_model: str,
    three_d_speaker_model: str,
    pyannote_model: str,
    enable_pyannote: bool = False,
) -> ModelRegistry:
    from model_adapters.funasr_adapter import FunASRTranscribeAdapter
    from model_adapters.pyannote_adapter import PyannoteDiarizationAdapter
    from model_adapters.three_d_speaker_adapter import (
        ThreeDSpeakerDiarizationAdapter,
        ThreeDSpeakerVoiceprintAdapter,
    )

    registry = ModelRegistry()

    asr_adapter = FunASRTranscribeAdapter(model_name=funasr_model)
    registry.register(
        asr_adapter.key,
        "transcription",
        asr_adapter,
        provider=asr_adapter.provider,
        display_name=asr_adapter.display_name,
        availability=asr_adapter.availability,
        experimental=asr_adapter.experimental,
    )

    diarization_adapter = ThreeDSpeakerDiarizationAdapter(model_name=three_d_speaker_model)
    registry.register(
        diarization_adapter.key,
        "diarization",
        diarization_adapter,
        provider=diarization_adapter.provider,
        display_name=diarization_adapter.display_name,
        availability=diarization_adapter.availability,
        experimental=diarization_adapter.experimental,
    )

    voiceprint_adapter = ThreeDSpeakerVoiceprintAdapter(model_name=three_d_speaker_model)
    registry.register(
        voiceprint_adapter.key,
        "voiceprint",
        voiceprint_adapter,
        provider=voiceprint_adapter.provider,
        display_name=voiceprint_adapter.display_name,
        availability=voiceprint_adapter.availability,
        experimental=voiceprint_adapter.experimental,
    )

    pyannote_adapter = PyannoteDiarizationAdapter(model_name=pyannote_model, enabled=enable_pyannote)
    registry.register(
        pyannote_adapter.key,
        "diarization",
        pyannote_adapter,
        provider=pyannote_adapter.provider,
        display_name=pyannote_adapter.display_name,
        availability=pyannote_adapter.availability,
        experimental=pyannote_adapter.experimental,
    )
    return registry
