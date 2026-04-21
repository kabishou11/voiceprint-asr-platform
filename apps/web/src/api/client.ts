import type {
  CreateTranscriptionResponse,
  CreateVoiceprintProfileResponse,
  EnrollVoiceprintResponse,
  IdentifyVoiceprintResponse,
  JobListResponse,
  ModelListResponse,
  TranscriptResponse,
  UploadAssetResponse,
  VerifyVoiceprintResponse,
  VoiceprintProfilesResponse,
} from './types';

const API_BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData
      ? init?.headers
      : {
          'Content-Type': 'application/json',
          ...(init?.headers ?? {}),
        },
    ...init,
  });

  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json') ? await response.json() : null;

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String(payload.detail)
        : `服务请求失败（${response.status}）`;
    throw new Error(detail);
  }

  return payload as T;
}

export function fetchJobs(): Promise<JobListResponse> {
  return request<JobListResponse>('/jobs');
}

export function fetchTranscript(jobId: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/transcriptions/${jobId}`);
}

export function uploadAudio(file: File): Promise<UploadAssetResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return request<UploadAssetResponse>('/assets/upload', {
    method: 'POST',
    body: formData,
  });
}

export function createTranscription(assetName: string, diarizationModel?: string) {
  return request<CreateTranscriptionResponse>('/transcriptions', {
    method: 'POST',
    body: JSON.stringify({ asset_name: assetName, diarization_model: diarizationModel || null }),
  });
}

export function fetchModels(): Promise<ModelListResponse> {
  return request<ModelListResponse>('/models');
}

export function fetchVoiceprintProfiles(): Promise<VoiceprintProfilesResponse> {
  return request<VoiceprintProfilesResponse>('/voiceprints/profiles');
}

export function createVoiceprintProfile(displayName: string, modelKey: string) {
  return request<CreateVoiceprintProfileResponse>('/voiceprints/profiles', {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName, model_key: modelKey }),
  });
}

export function enrollVoiceprint(profileId: string, assetName: string): Promise<EnrollVoiceprintResponse> {
  return request<EnrollVoiceprintResponse>(`/voiceprints/profiles/${profileId}/enroll`, {
    method: 'POST',
    body: JSON.stringify({ asset_name: assetName }),
  });
}

export function verifyVoiceprint(
  profileId: string,
  probeAssetName: string,
  threshold: number,
): Promise<VerifyVoiceprintResponse> {
  return request<VerifyVoiceprintResponse>('/voiceprints/verify', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, probe_asset_name: probeAssetName, threshold }),
  });
}

export function identifyVoiceprint(
  probeAssetName: string,
  topK: number,
): Promise<IdentifyVoiceprintResponse> {
  return request<IdentifyVoiceprintResponse>('/voiceprints/identify', {
    method: 'POST',
    body: JSON.stringify({ probe_asset_name: probeAssetName, top_k: topK }),
  });
}
