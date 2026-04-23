import { render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { AppLayout } from './AppLayout';
import { appTheme } from '../theme/appTheme';

const fetchJobs = vi.fn();
const fetchModels = vi.fn();

vi.mock('../api/client', () => ({
  fetchJobs: () => fetchJobs(),
  fetchModels: () => fetchModels(),
}));

describe('AppLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchJobs.mockResolvedValue({
      items: [
        {
          job_id: 'job-running',
          job_type: 'multi_speaker_transcription',
          status: 'running',
          created_at: '2026-04-23T08:00:00Z',
          updated_at: '2026-04-23T08:05:00Z',
          asset_name: 'meeting.wav',
        },
      ],
    });
    fetchModels.mockResolvedValue({
      gpu: {
        name: 'NVIDIA GeForce RTX 4060 Laptop GPU',
        total_memory_mb: 8192,
        used_memory_mb: 2048,
        cuda_available: true,
      },
      items: [
        {
          key: 'funasr-nano',
          display_name: 'FunASR Nano',
          task: 'transcription',
          provider: 'funasr',
          status: 'loaded',
          gpu_memory_mb: 1024,
          load_progress: null,
          error: null,
          experimental: false,
        },
      ],
    });
  });

  it('renders product navigation labels and global runtime state', async () => {
    render(
      <ThemeProvider theme={appTheme}>
        <CssBaseline />
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(fetchJobs).toHaveBeenCalled();
      expect(fetchModels).toHaveBeenCalled();
    });

    expect(screen.getByText('智能语音平台')).toBeInTheDocument();
    expect(screen.getAllByText('工作台').length).toBeGreaterThan(0);
    expect(screen.getByText('任务中心')).toBeInTheDocument();
    expect(screen.getAllByText('声纹库').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/运行中 1/).length).toBeGreaterThan(0);
  });
});
