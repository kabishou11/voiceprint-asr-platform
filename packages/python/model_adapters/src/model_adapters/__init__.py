from model_adapters.base import (
    ASRAdapter,
    AudioAsset,
    DiarizationAdapter,
    VoiceprintAdapter,
    resolve_audio_asset_path,
    resolve_model_reference,
)
from model_adapters.funasr_adapter import FunASRTranscribeAdapter
from model_adapters.pyannote_adapter import PyannoteDiarizationAdapter
from model_adapters.registry import ModelRegistry, RegistryEntry, build_default_registry
from model_adapters.three_d_speaker_adapter import (
    ThreeDSpeakerDiarizationAdapter,
    ThreeDSpeakerVoiceprintAdapter,
)

__all__ = [
    "ASRAdapter",
    "AudioAsset",
    "DiarizationAdapter",
    "VoiceprintAdapter",
    "FunASRTranscribeAdapter",
    "PyannoteDiarizationAdapter",
    "ModelRegistry",
    "RegistryEntry",
    "build_default_registry",
    "ThreeDSpeakerDiarizationAdapter",
    "ThreeDSpeakerVoiceprintAdapter",
    "resolve_audio_asset_path",
    "resolve_model_reference",
]


def __getattr__(name: str):
    if name == "FunASRNano":
        from model_adapters.funasr_nano_remote import FunASRNano

        return FunASRNano
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

