import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { TaskQueuePage } from './TaskQueuePage';
import { appTheme } from '../../theme/appTheme';

const fetchJobs = vi.fn();

vi.mock('../../api/client', () => ({
  fetchJobs: () => fetchJobs(),
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
          result: null,
          error_message: null,
        },
      ],
    });
  });

  it('explains that async jobs survive page refresh and remain visible', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchJobs).toHaveBeenCalled();
    });

    expect(
      await screen.findByText(/任务不会因为刷新界面而消失/),
    ).toBeInTheDocument();
    expect(screen.getByText(/自动轮询 5s/)).toBeInTheDocument();
    expect(screen.getAllByText('meeting.wav').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '展开详情' }));
    expect(screen.getByText(/结果暂不可用/)).toBeInTheDocument();
  });
});
