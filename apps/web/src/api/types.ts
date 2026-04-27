export type JobStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed';
export type JobType =
  | 'transcription'
  | 'multi_speaker_transcription'
  | 'diarization'
  | 'voiceprint_enroll'
  | 'voiceprint_verify'
  | 'voiceprint_identify';
export type ModelTask = 'transcription' | 'diarization' | 'voiceprint';
export type ModelAvailability = 'available' | 'optional' | 'unavailable';
export type ModelStatus = 'unloaded' | 'loading' | 'loaded' | 'load_failed';

export const TRANSCRIPTION_JOB_TYPES: JobType[] = ['transcription', 'multi_speaker_transcription'];

export function isTranscriptionJobType(jobType: JobType): boolean {
  return TRANSCRIPTION_JOB_TYPES.includes(jobType);
}

export const jobStatusLabels: Record<JobStatus, string> = {
  pending: '待处理',
  queued: '排队中',
  running: '处理中',
  succeeded: '已完成',
  failed: '失败',
};

export const jobTypeLabels: Record<JobType, string> = {
  transcription: '单人转写',
  multi_speaker_transcription: '多人转写',
  diarization: '说话人分离',
  voiceprint_enroll: '声纹注册',
  voiceprint_verify: '声纹验证',
  voiceprint_identify: '声纹识别',
};

export const modelTaskLabels: Record<ModelTask, string> = {
  transcription: '语音转写',
  diarization: '说话人分离',
  voiceprint: '声纹识别',
};

export const modelAvailabilityLabels: Record<ModelAvailability, string> = {
  available: '已就绪',
  optional: '按需启用',
  unavailable: '不可用',
};

export const providerLabels: Record<string, string> = {
  funasr: 'FunASR',
  '3dspeaker': '3D-Speaker',
  pyannote: 'pyannote',
};

export const modelStatusLabels: Record<ModelStatus, string> = {
  unloaded: '未加载',
  loading: '加载中',
  loaded: '已就绪',
  load_failed: '加载失败',
};

export interface Segment {
  start_ms: number;
  end_ms: number;
  text: string;
  speaker?: string | null;
  confidence?: number | null;
}

export interface TranscriptResult {
  text: string;
  language?: string | null;
  segments: Segment[];
  metadata?: TranscriptMetadata | null;
}

export interface TranscriptTimeline {
  label: string;
  source: string;
  segments: Segment[];
}

export interface TranscriptMetadata {
  timelines: TranscriptTimeline[];
  diarization_model?: string | null;
  alignment_source?: string | null;
}

export interface JobDetail {
  job_id: string;
  job_type: JobType;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  asset_name?: string | null;
  result?: TranscriptResult | null;
  error_message?: string | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface JobListResponse {
  items: JobDetail[];
  meta?: PaginationMeta;
}

export interface CreateTranscriptionResponse {
  job: JobDetail;
}

export interface CreateTranscriptionRequest {
  asset_name: string;
  asr_model?: string;
  diarization_model?: string | null;
  hotwords?: string[] | null;
  language?: string;
  vad_enabled?: boolean;
  itn?: boolean;
  num_speakers?: number | null;
  min_speakers?: number | null;
  max_speakers?: number | null;
}

export interface TranscriptResponse {
  job: JobDetail;
  transcript?: TranscriptResult | null;
}

export interface SpeakerMinuteStats {
  speaker: string;
  segment_count: number;
  duration_ms: number;
}

export interface MeetingMinutesResponse {
  job_id: string;
  title: string;
  summary: string;
  key_points: string[];
  topics: string[];
  decisions: string[];
  action_items: string[];
  risks: string[];
  keywords: string[];
  speaker_stats: SpeakerMinuteStats[];
  markdown: string;
  mode?: 'local' | 'llm';
  model?: string | null;
  reasoning?: string | null;
}

export interface ModelInfo {
  key: string;
  display_name: string;
  task: ModelTask;
  provider: string;
  availability: ModelAvailability;
  experimental: boolean;
}

export interface ModelListResponse {
  items: ModelInfo[];
}

export interface GPUInfo {
  name: string | null;
  total_memory_mb: number | null;
  used_memory_mb: number | null;
  cuda_available: boolean;
}

export interface ModelInfoWithStatus {
  key: string;
  display_name: string;
  task: ModelTask;
  provider: string;
  availability?: ModelAvailability;
  status: ModelStatus;
  gpu_memory_mb: number | null;
  load_progress: number | null;
  error: string | null;
  experimental: boolean;
}

export interface ModelLoadResponse {
  key: string;
  status: ModelStatus;
  gpu_memory_mb: number | null;
  error: string | null;
}

export interface ModelUnloadResponse {
  key: string;
  status: ModelStatus;
  released_mb: number | null;
}

export interface ModelListWithGPUResponse {
  items: ModelInfoWithStatus[];
  gpu: GPUInfo;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  broker_available: boolean;
  worker_available: boolean;
  async_available: boolean;
  execution_mode?: 'async' | 'sync';
  broker_error?: string | null;
  worker_error?: string | null;
}

export interface UploadAssetResponse {
  asset_name: string;
  original_filename: string;
  size: number;
}

export interface VoiceprintProfile {
  profile_id: string;
  display_name: string;
  model_key: string;
  sample_count: number;
}

export interface VoiceprintProfilesResponse {
  items: VoiceprintProfile[];
}

export interface CreateVoiceprintProfileResponse {
  profile: VoiceprintProfile;
}

export interface VoiceprintEnrollmentResult {
  profile_id: string;
  asset_name: string;
  status: string;
  mode: string;
}

export interface VoiceprintAsyncReceipt {
  status: 'queued' | 'running';
  job_id: string;
}

export interface EnrollVoiceprintResponse {
  profile?: VoiceprintProfile | null;
  enrollment?: VoiceprintEnrollmentResult | null;
  job?: VoiceprintAsyncReceipt | null;
}

export interface VoiceprintVerificationResult {
  profile_id: string;
  score: number;
  threshold: number;
  matched: boolean;
}

export interface VerifyVoiceprintResponse {
  result?: VoiceprintVerificationResult | null;
  job?: VoiceprintAsyncReceipt | null;
}

export interface VoiceprintIdentificationCandidate {
  profile_id: string;
  display_name: string;
  score: number;
  rank: number;
}

export interface VoiceprintIdentificationResult {
  candidates: VoiceprintIdentificationCandidate[];
  matched: boolean;
}

export interface IdentifyVoiceprintResponse {
  result?: VoiceprintIdentificationResult | null;
  job?: VoiceprintAsyncReceipt | null;
}

export interface VoiceprintJobResponse {
  job_id: string;
  job_type: Extract<JobType, 'voiceprint_enroll' | 'voiceprint_verify' | 'voiceprint_identify'>;
  status: JobStatus;
  asset_name?: string | null;
  error_message?: string | null;
  enrollment?: VoiceprintEnrollmentResult | null;
  verification?: VoiceprintVerificationResult | null;
  identification?: VoiceprintIdentificationResult | null;
}

export function formatDateTime(value?: string | null): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}
