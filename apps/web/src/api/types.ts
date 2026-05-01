export type JobStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed';
export type JobType =
  | 'transcription'
  | 'multi_speaker_transcription'
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
  voiceprint_matches?: Array<{
    speaker: string;
    scope_mode: 'none' | 'all' | 'group';
    scope_group_id?: string | null;
    candidate_profile_ids: string[];
    candidates: VoiceprintIdentificationCandidate[];
    matched: boolean;
    error?: string | null;
  }>;
}

export interface CorePipelineEvaluationResponse {
  job_id?: string;
  summary?: Record<string, unknown>;
  asr?: Record<string, unknown>;
  speakers?: Record<string, unknown>;
  speaker_reference?: Record<string, unknown>;
  voiceprint?: Record<string, unknown>;
  voiceprint_threshold_scan?: Record<string, unknown>;
  minutes?: Record<string, unknown>;
}

export interface JobDetail {
  job_id: string;
  job_type: JobType;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  asset_name?: string | null;
  result?: TranscriptResult | Record<string, unknown> | null;
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
  voiceprint_scope_mode?: 'none' | 'all' | 'group';
  voiceprint_group_id?: string | null;
  voiceprint_profile_ids?: string[] | null;
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
  evidence?: Record<string, Array<Record<string, unknown>>> | null;
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

export interface AudioDecoderInfo {
  backend: 'ffmpeg' | 'torchaudio' | 'none';
  ffmpeg_available: boolean;
  ffmpeg_path: string | null;
  torchaudio_available: boolean;
  warning: string | null;
}

export interface MeetingMinutesLLMInfo {
  configured: boolean;
  model: string;
  base_url: string;
  reasoning_split: boolean;
  timeout_seconds: number;
  warning: string | null;
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

export interface WorkerModelInfo {
  key: string;
  display_name: string;
  task: ModelTask;
  provider: string;
  availability: ModelAvailability;
  experimental: boolean;
}

export interface WorkerModelStatusResponse {
  online: boolean;
  source: string;
  hostname: string | null;
  items: WorkerModelInfo[];
  gpu: GPUInfo | null;
  error: string | null;
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
  audio_decoder: AudioDecoderInfo;
  worker_model_status?: WorkerModelStatusResponse | null;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  audio_decoder: AudioDecoderInfo;
  meeting_minutes_llm: MeetingMinutesLLMInfo;
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

export interface VoiceprintGroup {
  group_id: string;
  display_name: string;
  profile_ids: string[];
}

export interface VoiceprintProfilesResponse {
  items: VoiceprintProfile[];
}

export interface VoiceprintGroupsResponse {
  items: VoiceprintGroup[];
}

export interface CreateVoiceprintProfileResponse {
  profile: VoiceprintProfile;
}

export interface VoiceprintEnrollmentResult {
  profile_id: string;
  asset_name: string;
  status: string;
  mode: string;
  quality?: Record<string, unknown> | null;
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
