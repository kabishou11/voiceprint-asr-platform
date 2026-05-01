import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import { TranscriptionWorkbenchPage } from './TranscriptionWorkbenchPage';
import { appTheme } from '../../theme/appTheme';

const fetchModels = vi.fn();
const fetchJobs = vi.fn();
const fetchVoiceprintGroups = vi.fn();
const fetchVoiceprintProfiles = vi.fn();
const uploadAudio = vi.fn();
const createTranscription = vi.fn();

vi.mock('../../api/client', () => ({
  fetchModels: () => fetchModels(),
  fetchJobs: () => fetchJobs(),
  fetchVoiceprintGroups: () => fetchVoiceprintGroups(),
  fetchVoiceprintProfiles: () => fetchVoiceprintProfiles(),
  uploadAudio: (...args: unknown[]) => uploadAudio(...args),
  createTranscription: (...args: unknown[]) => createTranscription(...args),
}));

function renderPage(initialEntry = '/') {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/" element={<TranscriptionWorkbenchPage />} />
          <Route path="/jobs/:jobId" element={<div>任务详情页</div>} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('TranscriptionWorkbenchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchModels.mockResolvedValue({
      gpu: {
        name: 'NVIDIA GeForce RTX 4060 Laptop GPU',
        total_memory_mb: 8192,
        used_memory_mb: 2048,
        cuda_available: true,
      },
      audio_decoder: {
        backend: 'ffmpeg',
        ffmpeg_available: true,
        ffmpeg_path: 'C:/ffmpeg/bin/ffmpeg.exe',
        torchaudio_available: true,
        warning: null,
      },
      items: [
        {
          key: 'funasr-nano',
          display_name: 'FunASR Nano',
          task: 'transcription',
          provider: 'funasr',
          status: 'unloaded',
          gpu_memory_mb: null,
          load_progress: null,
          error: null,
          experimental: false,
        },
        {
          key: '3dspeaker-diarization',
          display_name: '3D-Speaker Diarization',
          task: 'diarization',
          provider: '3dspeaker',
          status: 'loaded',
          gpu_memory_mb: 1024,
          load_progress: null,
          error: null,
          experimental: false,
        },
        {
          key: '3dspeaker-embedding',
          display_name: '3D-Speaker Voiceprint',
          task: 'voiceprint',
          provider: '3dspeaker',
          status: 'unloaded',
          gpu_memory_mb: null,
          load_progress: null,
          error: null,
          experimental: false,
        },
        {
          key: 'pyannote-community-1',
          display_name: 'pyannote Community-1',
          task: 'diarization',
          provider: 'pyannote',
          status: 'load_failed',
          gpu_memory_mb: null,
          load_progress: null,
          error: 'missing gated weights',
          experimental: false,
        },
      ],
    });
    fetchJobs.mockResolvedValue({
      items: [
        {
          job_id: 'job-1',
          job_type: 'multi_speaker_transcription',
          status: 'succeeded',
          created_at: '2026-04-21T10:00:00Z',
          updated_at: '2026-04-21T10:01:00Z',
          asset_name: 'meeting.wav',
        },
      ],
    });
    fetchVoiceprintGroups.mockResolvedValue({ items: [] });
    fetchVoiceprintProfiles.mockResolvedValue({ items: [] });
    uploadAudio.mockResolvedValue({
      asset_name: 'uploaded.wav',
      original_filename: 'meeting.wav',
      size: 123,
    });
    createTranscription.mockResolvedValue({
      job: {
        job_id: 'job-2',
        job_type: 'multi_speaker_transcription',
        status: 'queued',
        created_at: '2026-04-21T10:10:00Z',
        updated_at: '2026-04-21T10:10:00Z',
        asset_name: 'uploaded.wav',
      },
    });
  });

  it('submits advanced transcription options', async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
      expect(fetchJobs).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByText('高级设置'));
    fireEvent.change(screen.getByLabelText('热词'), { target: { value: '阿里云, FunASR\n说话人分离' } });
    fireEvent.change(screen.getByLabelText('已知说话人数'), { target: { value: '3' } });
    fireEvent.click(screen.getByLabelText('启用 VAD'));

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['meeting'], 'meeting.wav', { type: 'audio/wav' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '立即开始' }));

    await waitFor(() => {
      expect(uploadAudio).toHaveBeenCalled();
      expect(createTranscription).toHaveBeenCalledWith({
        asset_name: 'uploaded.wav',
        asr_model: 'funasr-nano',
        diarization_model: '3dspeaker-diarization',
        hotwords: ['阿里云', 'FunASR', '说话人分离'],
        language: 'zh-cn',
        vad_enabled: false,
        itn: true,
        voiceprint_scope_mode: 'none',
        voiceprint_group_id: null,
        num_speakers: 3,
        min_speakers: null,
        max_speakers: null,
      });
    });
    expect(await screen.findByText('任务详情页')).toBeInTheDocument();
  });

  it('prefills asset and baseline parameters from retry query', async () => {
    renderPage('/?asset=meeting.wav&language=en&mode=single');

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
      expect(fetchJobs).toHaveBeenCalled();
    });

    expect(screen.getByText(/已带入历史任务参数/)).toBeInTheDocument();
    expect(screen.getAllByText(/当前将使用资产：meeting\.wav/).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('语言')).toHaveTextContent('英文');

    fireEvent.click(screen.getByRole('button', { name: '立即开始' }));

    await waitFor(() => {
      expect(createTranscription).toHaveBeenCalledWith({
        asset_name: 'meeting.wav',
        asr_model: 'funasr-nano',
        diarization_model: null,
        hotwords: null,
        language: 'en',
        vad_enabled: true,
        itn: true,
        voiceprint_scope_mode: 'none',
        voiceprint_group_id: null,
        num_speakers: null,
        min_speakers: null,
        max_speakers: null,
      });
    });
  });

  it('shows current local model state when 3dspeaker is ready but pyannote is unavailable', async () => {
    renderPage();

    expect(await screen.findByText('ASR 可加载')).toBeInTheDocument();
    expect(screen.getByText('分离 已就绪')).toBeInTheDocument();
    expect(screen.getByText('pyannote 未启用')).toBeInTheDocument();
    expect(screen.getByText('开始任务')).toBeInTheDocument();
  });

  it('warns before uploading compressed audio when decoder backend is unavailable', async () => {
    fetchModels.mockResolvedValueOnce({
      gpu: {
        name: 'NVIDIA GeForce RTX 4060 Laptop GPU',
        total_memory_mb: 8192,
        used_memory_mb: 2048,
        cuda_available: true,
      },
      audio_decoder: {
        backend: 'none',
        ffmpeg_available: false,
        ffmpeg_path: null,
        torchaudio_available: false,
        warning: '没有可用音频解码器',
      },
      items: [
        {
          key: 'funasr-nano',
          display_name: 'FunASR Nano',
          task: 'transcription',
          provider: 'funasr',
          status: 'unloaded',
          gpu_memory_mb: null,
          load_progress: null,
          error: null,
          experimental: false,
        },
      ],
    });
    const { container } = renderPage();

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
    });

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['meeting'], 'meeting.m4a', { type: 'audio/mp4' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(await screen.findByText(/当前后端没有可用音频解码器/)).toBeInTheDocument();
    expect(screen.getByText(/建议安装 ffmpeg/)).toBeInTheDocument();
  });
});
