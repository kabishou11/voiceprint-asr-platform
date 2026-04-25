import type {
  CreateTranscriptionRequest,
  CreateTranscriptionResponse,
  CreateVoiceprintProfileResponse,
  HealthResponse,
  EnrollVoiceprintResponse,
  IdentifyVoiceprintResponse,
  JobListResponse,
  MeetingMinutesResponse,
  ModelListWithGPUResponse,
  ModelLoadResponse,
  ModelUnloadResponse,
  TranscriptResponse,
  UploadAssetResponse,
  VerifyVoiceprintResponse,
  VoiceprintJobResponse,
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

export function fetchJobs(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  job_type?: string;
  keyword?: string;
}): Promise<JobListResponse> {
  const search = new URLSearchParams();
  if (params?.page) search.set('page', String(params.page));
  if (params?.page_size) search.set('page_size', String(params.page_size));
  if (params?.status) search.set('status', params.status);
  if (params?.job_type) search.set('job_type', params.job_type);
  if (params?.keyword) search.set('keyword', params.keyword);
  return request<JobListResponse>(`/jobs${search.size ? `?${search.toString()}` : ''}`);
}

export function fetchVoiceprintJob(jobId: string): Promise<VoiceprintJobResponse> {
  return request<VoiceprintJobResponse>(`/voiceprints/jobs/${jobId}`);
}

export function deleteJob(jobId: string): Promise<{ job_id: string; deleted: boolean }> {
  return request<{ job_id: string; deleted: boolean }>(`/jobs/${jobId}`, { method: 'DELETE' });
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function fetchTranscript(jobId: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/transcriptions/${jobId}`);
}

export function fetchMeetingMinutes(jobId: string): Promise<MeetingMinutesResponse> {
  return request<MeetingMinutesResponse>(`/transcriptions/${jobId}/minutes`);
}

export function generateMeetingMinutes(jobId: string, useLlm = true): Promise<MeetingMinutesResponse> {
  return request<MeetingMinutesResponse>(`/transcriptions/${jobId}/minutes?use_llm=${String(useLlm)}`, {
    method: 'POST',
  });
}

export function uploadAudio(file: File): Promise<UploadAssetResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return request<UploadAssetResponse>('/assets/upload', {
    method: 'POST',
    body: formData,
  });
}

export function createTranscription(payload: CreateTranscriptionRequest) {
  return request<CreateTranscriptionResponse>('/transcriptions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchModels(): Promise<ModelListWithGPUResponse> {
  return request<ModelListWithGPUResponse>('/models');
}

export function loadModel(modelKey: string): Promise<ModelLoadResponse> {
  return request<ModelLoadResponse>(`/models/${modelKey}/load`, { method: 'POST' });
}

export function unloadModel(modelKey: string): Promise<ModelUnloadResponse> {
  return request<ModelUnloadResponse>(`/models/${modelKey}`, { method: 'DELETE' });
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
