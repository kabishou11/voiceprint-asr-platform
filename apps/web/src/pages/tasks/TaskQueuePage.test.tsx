import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, vi } from 'vitest';

import { TaskQueuePage } from './TaskQueuePage';
import { appTheme } from '../../theme/appTheme';

const fetchJobs = vi.fn();
const fetchHealth = vi.fn();
const deleteJob = vi.fn();
const cancelJob = vi.fn();
const retryJob = vi.fn();

vi.mock('../../api/client', () => ({
  fetchJobs: () => fetchJobs(),
  fetchHealth: () => fetchHealth(),
  deleteJob: (...args: unknown[]) => deleteJob(...args),
  cancelJob: (...args: unknown[]) => cancelJob(...args),
  retryJob: (...args: unknown[]) => retryJob(...args),
}));

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter>
        <TaskQueuePage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('TaskQueuePage', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    fetchHealth.mockResolvedValue({
      status: 'ok',
      app_name: 'voiceprint-asr-platform',
      broker_available: true,
      worker_available: false,
      async_available: false,
      execution_mode: 'sync',
      broker_error: null,
      worker_error: 'worker_offline',
    });
    fetchJobs.mockResolvedValue({
      items: [
        {
          job_id: 'job-running',
          job_type: 'multi_speaker_transcription',
          status: 'running',
          created_at: '2026-04-23T08:00:00Z',
          updated_at: '2026-04-23T08:05:00Z',
          asset_name: 'meeting.wav',
          result: null,
          error_message: null,
        },
      ],
    });
    deleteJob.mockResolvedValue({ job_id: 'job-running', deleted: true });
    retryJob.mockResolvedValue({
      job_id: 'job-retry',
      job_type: 'multi_speaker_transcription',
      status: 'queued',
      created_at: '2026-04-23T08:07:00Z',
      updated_at: '2026-04-23T08:07:00Z',
      asset_name: 'meeting.wav',
      result: null,
      error_message: null,
    });
    cancelJob.mockResolvedValue({
      job_id: 'job-running',
      job_type: 'multi_speaker_transcription',
      status: 'canceled',
      created_at: '2026-04-23T08:00:00Z',
      updated_at: '2026-04-23T08:06:00Z',
      asset_name: 'meeting.wav',
      result: null,
      error_message: '用户取消任务',
      status_explanation: '任务已取消',
    });
  });

  it('shows queue blockage and allows deleting stuck jobs', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchJobs).toHaveBeenCalled();
      expect(fetchHealth).toHaveBeenCalled();
    });

    expect(await screen.findByText('任务队列')).toBeInTheDocument();
    expect(screen.getAllByText(/Worker 未连接/).length).toBeGreaterThan(0);
    expect(screen.getByText(/worker_offline/)).toBeInTheDocument();
    expect(screen.getByText('队列未就绪')).toBeInTheDocument();
    expect(screen.getByText(/自动轮询 5s/)).toBeInTheDocument();
    expect(screen.getAllByText('meeting.wav').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '展开详情' }));
    expect(screen.getAllByText(/不会继续推进/).length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    await waitFor(() => {
      expect(cancelJob).toHaveBeenCalledWith('job-running');
    });
    expect(await screen.findByText('已取消')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() => {
      expect(deleteJob).toHaveBeenCalledWith('job-running');
    });
  });

  it('explains broker outage as fail-fast instead of a stuck queue', async () => {
    fetchHealth.mockResolvedValueOnce({
      status: 'ok',
      app_name: 'voiceprint-asr-platform',
      broker_available: false,
      worker_available: false,
      async_available: false,
      execution_mode: 'sync',
      broker_error: 'connection refused',
      worker_error: 'broker_unavailable',
    });

    renderPage();

    expect(await screen.findByText('异步队列不可用')).toBeInTheDocument();
    expect(screen.getAllByText(/默认会快速失败/).length).toBeGreaterThan(0);
    expect(screen.getByText(/connection refused/)).toBeInTheDocument();
    expect(screen.queryByText(/建议删除卡住任务后重建/)).not.toBeInTheDocument();
  });

  it('retries failed jobs using the backend retry endpoint', async () => {
    fetchJobs.mockResolvedValueOnce({
      items: [
        {
          job_id: 'job-failed',
          job_type: 'multi_speaker_transcription',
          status: 'failed',
          created_at: '2026-04-23T08:00:00Z',
          updated_at: '2026-04-23T08:06:00Z',
          asset_name: 'meeting.wav',
          result: null,
          error_message: 'worker_offline',
        },
      ],
    });

    renderPage();

    expect((await screen.findAllByText('任务队列')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await waitFor(() => {
      expect(retryJob).toHaveBeenCalledWith('job-failed');
    });
    expect(await screen.findByText(/job-retry/)).toBeInTheDocument();
  });
});
