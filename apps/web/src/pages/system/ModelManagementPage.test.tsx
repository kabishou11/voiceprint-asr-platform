import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { ModelManagementPage } from './ModelManagementPage';
import { appTheme } from '../../theme/appTheme';

const fetchModels = vi.fn();
const loadModel = vi.fn();
const unloadModel = vi.fn();
const warmupWorkerModel = vi.fn();

vi.mock('../../api/client', () => ({
  fetchModels: () => fetchModels(),
  loadModel: (...args: unknown[]) => loadModel(...args),
  unloadModel: (...args: unknown[]) => unloadModel(...args),
  warmupWorkerModel: (...args: unknown[]) => warmupWorkerModel(...args),
}));

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter>
        <ModelManagementPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('ModelManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchModels.mockResolvedValue({
      gpu: {
        name: 'NVIDIA GeForce RTX 4060 Laptop GPU',
        total_memory_mb: 8192,
        used_memory_mb: 2048,
        cuda_available: true,
      },
      worker_model_status: {
        online: true,
        source: 'celery_task',
        hostname: 'worker-1',
        gpu: {
          name: 'NVIDIA GeForce RTX 4060 Laptop GPU',
          total_memory_mb: 8192,
          used_memory_mb: 1024,
          cuda_available: true,
        },
        error: null,
        items: [
          {
            key: 'funasr-nano',
            display_name: 'FunASR Nano',
            task: 'transcription',
            provider: 'funasr',
            availability: 'available',
            runtime_status: 'loaded',
            loaded: true,
            gpu_memory_mb: 1024,
            error: null,
            experimental: false,
          },
          {
            key: '3dspeaker-diarization',
            display_name: '3D-Speaker Diarization',
            task: 'diarization',
            provider: '3dspeaker',
            availability: 'available',
            runtime_status: 'unloaded',
            loaded: false,
            gpu_memory_mb: null,
            error: null,
            experimental: false,
          },
        ],
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
        {
          key: '3dspeaker-diarization',
          display_name: '3D-Speaker Diarization',
          task: 'diarization',
          provider: '3dspeaker',
          status: 'unloaded',
          gpu_memory_mb: null,
          load_progress: null,
          error: null,
          experimental: false,
        },
      ],
    });
    loadModel.mockResolvedValue({});
    unloadModel.mockResolvedValue({});
    warmupWorkerModel.mockResolvedValue({});
  });

  it('surfaces gpu runtime control and load/unload actions', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
    });

    expect((await screen.findAllByText('模型')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/已加载 1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/RTX 4060/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Worker 模型状态：在线/)).toBeInTheDocument();
    expect(screen.getAllByText(/已加载 1 个/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Worker: 已就绪').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: '加载' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '卸载' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '预热 Worker' }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole('button', { name: '加载' })[0]);

    await waitFor(() => {
      expect(loadModel).toHaveBeenCalledWith('3dspeaker-diarization');
    });
  });

  it('warms up the selected model in worker process', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
    });

    fireEvent.click(screen.getAllByRole('button', { name: '预热 Worker' })[0]);

    await waitFor(() => {
      expect(warmupWorkerModel).toHaveBeenCalledWith('funasr-nano');
    });
  });
});
