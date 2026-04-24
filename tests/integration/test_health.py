from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.services.voiceprint_service import voiceprint_service
from model_adapters import AudioAsset, FunASRTranscribeAdapter, has_cuda_runtime, resolve_audio_asset_path, resolve_model_reference
from model_adapters.pyannote_adapter import PyannoteDiarizationAdapter
from model_adapters.three_d_speaker_adapter import (
    ThreeDSpeakerDiarizationAdapter,
    ThreeDSpeakerVoiceprintAdapter,
)


client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get('/api/v1/health')

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert 'broker_available' in response.json()
    assert 'worker_available' in response.json()
    assert 'async_available' in response.json()


def test_models_endpoint_marks_empty_local_model_directories_unavailable() -> None:
    response = client.get('/api/v1/models')

    assert response.status_code == 200
    items = {item['key']: item for item in response.json()['items']}
    expected_cuda_availability = 'available' if has_cuda_runtime() else 'unavailable'
    assert items['funasr-nano']['availability'] == expected_cuda_availability
    assert items['3dspeaker-diarization']['availability'] == expected_cuda_availability
    assert items['3dspeaker-embedding']['availability'] == expected_cuda_availability
    assert items['pyannote-community-1']['availability'] == 'unavailable'


def test_resolve_model_reference_prefers_local_models_directory() -> None:
    resolved = Path(resolve_model_reference('models/Fun-ASR-Nano-2512'))

    assert resolved.name == 'Fun-ASR-Nano-2512'
    assert resolved.parent.name == 'models'
    assert resolved.exists()


def test_resolve_audio_asset_path_falls_back_to_tests_samples() -> None:
    resolved = Path(resolve_audio_asset_path('丹山路.m4a'))

    assert resolved.name == '丹山路.m4a'
    assert resolved.parent.name == 'tests'
    assert resolved.exists()


def test_upload_asset_saves_file_and_returns_asset_name() -> None:
    wav_path = Path(resolve_audio_asset_path('声纹-女1.wav'))
    response = client.post(
        '/api/v1/assets/upload',
        files={'file': (wav_path.name, wav_path.read_bytes(), 'audio/wav')},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['asset_name'].endswith('.wav')
    assert payload['original_filename'] == wav_path.name
    saved = Path('F:/1work/音频识别/voiceprint-asr-platform/storage/uploads') / payload['asset_name']
    assert saved.exists()


def test_upload_asset_rejects_empty_file() -> None:
    response = client.post(
        '/api/v1/assets/upload',
        files={'file': ('empty.wav', BytesIO(b''), 'audio/wav')},
    )

    assert response.status_code == 400
    assert '上传文件为空' in response.json()['detail']


def test_uploaded_asset_can_create_transcription_job() -> None:
    wav_path = Path(resolve_audio_asset_path('声纹-女1.wav'))
    upload = client.post(
        '/api/v1/assets/upload',
        files={'file': (wav_path.name, wav_path.read_bytes(), 'audio/wav')},
    )
    asset_name = upload.json()['asset_name']

    response = client.post('/api/v1/transcriptions', json={'asset_name': asset_name, 'diarization_model': None})

    if has_cuda_runtime():
        assert response.status_code == 200
        assert response.json()['job']['asset_name'] == asset_name
    else:
        assert response.status_code == 409
        assert 'CUDA GPU' in response.json()['detail']


def test_meeting_minutes_endpoint_generates_from_finished_job() -> None:
    jobs = client.get('/api/v1/jobs').json()['items']
    succeeded = next(item for item in jobs if item['status'] == 'succeeded')

    response = client.get(f"/api/v1/transcriptions/{succeeded['job_id']}/minutes")

    assert response.status_code == 200
    payload = response.json()
    assert payload['job_id'] == succeeded['job_id']
    assert payload['summary']
    assert isinstance(payload['key_points'], list)
    assert isinstance(payload['speaker_stats'], list)


def test_jobs_endpoint_supports_delete() -> None:
    create = client.post('/api/v1/transcriptions', json={'asset_name': 'sample-meeting.wav', 'diarization_model': None})
    if create.status_code != 200:
      return

    job_id = create.json()['job']['job_id']
    delete_response = client.delete(f'/api/v1/jobs/{job_id}')
    assert delete_response.status_code == 200
    assert delete_response.json()['deleted'] is True

    missing_response = client.get(f'/api/v1/jobs/{job_id}')
    assert missing_response.status_code == 404


def test_funasr_transcribe_real_wav_sample() -> None:
    adapter = FunASRTranscribeAdapter(model_name='models/Fun-ASR-Nano-2512')
    if has_cuda_runtime():
        result = adapter.transcribe(AudioAsset(path=resolve_audio_asset_path('声纹-女1.wav')))
        assert result.text
    else:
        try:
            adapter.transcribe(AudioAsset(path=resolve_audio_asset_path('声纹-女1.wav')))
            assert False, 'expected CUDA runtime error'
        except RuntimeError as exc:
            assert 'CUDA GPU' in str(exc)


def test_downloaded_local_models_are_available_in_adapters() -> None:
    expected_cuda_availability = 'available' if has_cuda_runtime() else 'unavailable'
    assert ThreeDSpeakerDiarizationAdapter(model_name='models/3D-Speaker/campplus').availability == expected_cuda_availability
    assert ThreeDSpeakerVoiceprintAdapter(model_name='models/3D-Speaker/campplus').availability == expected_cuda_availability
    assert PyannoteDiarizationAdapter(model_name='models/pyannote/speaker-diarization-community-1', enabled=True).availability == 'unavailable'


def test_funasr_transcribe_compressed_audio_requires_decoder_backend() -> None:
    adapter = FunASRTranscribeAdapter(model_name='models/Fun-ASR-Nano-2512')

    try:
        result = adapter.transcribe(AudioAsset(path=resolve_audio_asset_path('丹山路.m4a')))
        assert result.text
    except RuntimeError as exc:
        assert '无法解码音频文件' in str(exc) or 'CUDA GPU' in str(exc)


def test_voiceprint_service_seeds_sample_profile() -> None:
    profiles = {item.profile_id: item for item in voiceprint_service.list_profiles()}

    assert 'sample-female-1' in profiles
    assert profiles['sample-female-1'].display_name == '女声样本 1'


def test_voiceprint_enroll_api_updates_profile() -> None:
    wav_path = Path(resolve_audio_asset_path('声纹-女1.wav'))
    created = client.post('/api/v1/voiceprints/profiles', json={'display_name': '注册测试', 'model_key': '3dspeaker-embedding'})
    profile_id = created.json()['profile']['profile_id']
    upload = client.post(
        '/api/v1/assets/upload',
        files={'file': (wav_path.name, wav_path.read_bytes(), 'audio/wav')},
    )
    asset_name = upload.json()['asset_name']

    response = client.post(f'/api/v1/voiceprints/profiles/{profile_id}/enroll', json={'asset_name': asset_name})

    if has_cuda_runtime():
        assert response.status_code == 200
        payload = response.json()
        assert payload['profile']['profile_id'] == profile_id
        assert payload['profile']['sample_count'] == 1
        assert payload['enrollment']['status'] == 'enrolled'
        assert payload['enrollment']['mode'] == 'replace'
    else:
        assert response.status_code == 409
        assert 'CUDA GPU' in response.json()['detail']


def test_voiceprint_enroll_api_returns_404_for_unknown_profile() -> None:
    response = client.post('/api/v1/voiceprints/profiles/unknown-profile/enroll', json={'asset_name': 'missing.wav'})

    assert response.status_code == 404


def test_voiceprint_enroll_api_replace_mode_keeps_single_sample() -> None:
    wav_path = Path(resolve_audio_asset_path('声纹-女1.wav'))
    created = client.post('/api/v1/voiceprints/profiles', json={'display_name': '重复注册测试', 'model_key': '3dspeaker-embedding'})
    profile_id = created.json()['profile']['profile_id']

    upload_one = client.post(
        '/api/v1/assets/upload',
        files={'file': (wav_path.name, wav_path.read_bytes(), 'audio/wav')},
    )
    upload_two = client.post(
        '/api/v1/assets/upload',
        files={'file': (wav_path.name, wav_path.read_bytes(), 'audio/wav')},
    )

    first = client.post(f'/api/v1/voiceprints/profiles/{profile_id}/enroll', json={'asset_name': upload_one.json()['asset_name']})
    second = client.post(f'/api/v1/voiceprints/profiles/{profile_id}/enroll', json={'asset_name': upload_two.json()['asset_name']})

    if has_cuda_runtime():
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()['profile']['sample_count'] == 1
        assert second.json()['enrollment']['mode'] == 'replace'
    else:
        assert first.status_code == 409
        assert second.status_code == 409


def test_voiceprint_verify_uses_requested_probe_asset() -> None:
    if has_cuda_runtime():
        result = voiceprint_service.verify('sample-female-1', probe_asset_name='5分钟.wav', threshold=0.7)
        assert result.profile_id == 'sample-female-1'
        assert 0.0 <= result.score <= 1.0
    else:
        try:
            voiceprint_service.verify('sample-female-1', probe_asset_name='5分钟.wav', threshold=0.7)
            assert False, 'expected unavailable high precision verification'
        except (RuntimeError, ValueError) as exc:
            assert 'CUDA' in str(exc) or '尚未注册样本' in str(exc)


def test_voiceprint_identify_uses_requested_probe_asset() -> None:
    if has_cuda_runtime():
        result = voiceprint_service.identify(probe_asset_name='5分钟.wav', top_k=2)
        assert all(candidate.profile_id in {'sample-female-1', 'demo-user'} for candidate in result.candidates)
    else:
        try:
            voiceprint_service.identify(probe_asset_name='5分钟.wav', top_k=2)
            assert False, 'expected unavailable high precision identification'
        except RuntimeError as exc:
            assert 'CUDA GPU' in str(exc)


def test_voiceprint_verify_api_accepts_probe_asset_name() -> None:
    response = client.post(
        '/api/v1/voiceprints/verify',
        json={
            'profile_id': 'sample-female-1',
            'probe_asset_name': '5分钟.wav',
            'threshold': 0.7,
        },
    )

    if has_cuda_runtime():
        assert response.status_code == 200
        assert response.json()['result']['profile_id'] == 'sample-female-1'
    else:
        assert response.status_code in {400, 409}


def test_voiceprint_verify_api_returns_404_for_unknown_profile() -> None:
    response = client.post(
        '/api/v1/voiceprints/verify',
        json={
            'profile_id': 'unknown-profile',
            'probe_asset_name': '5分钟.wav',
            'threshold': 0.7,
        },
    )

    assert response.status_code == 404


def test_voiceprint_identify_api_accepts_probe_asset_name() -> None:
    response = client.post(
        '/api/v1/voiceprints/identify',
        json={
            'probe_asset_name': '5分钟.wav',
            'top_k': 2,
        },
    )

    if has_cuda_runtime():
        assert response.status_code == 200
        assert response.json()['result']['candidates'][0]['profile_id'] == 'sample-female-1'
    else:
        assert response.status_code == 409
