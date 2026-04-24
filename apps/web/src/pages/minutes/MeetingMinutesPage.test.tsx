import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import { MeetingMinutesPage } from './MeetingMinutesPage';
import { appTheme } from '../../theme/appTheme';

const fetchTranscript = vi.fn();
const fetchMeetingMinutes = vi.fn();
const generateMeetingMinutes = vi.fn();

vi.mock('../../api/client', () => ({
  fetchTranscript: (...args: unknown[]) => fetchTranscript(...args),
  fetchMeetingMinutes: (...args: unknown[]) => fetchMeetingMinutes(...args),
  generateMeetingMinutes: (...args: unknown[]) => generateMeetingMinutes(...args),
}));

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter initialEntries={['/minutes/job-1']}>
        <Routes>
          <Route path="/minutes/:jobId" element={<MeetingMinutesPage />} />
          <Route path="/jobs/:jobId" element={<div>原文页</div>} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('MeetingMinutesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchTranscript.mockResolvedValue({
      job: {
        job_id: 'job-1',
        job_type: 'multi_speaker_transcription',
        status: 'succeeded',
        created_at: '2026-04-21T10:00:00Z',
        updated_at: '2026-04-21T10:02:00Z',
        asset_name: 'meeting.wav',
      },
      transcript: {
        text: '我们需要跟进方案。',
        language: 'zh-cn',
        segments: [{ start_ms: 0, end_ms: 2000, text: '我们需要跟进方案。', speaker: 'SPEAKER_00' }],
      },
    });
    fetchMeetingMinutes.mockResolvedValue({
      job_id: 'job-1',
      title: 'meeting.wav',
      summary: '会议讨论了方案跟进。',
      key_points: ['方案需要继续推进'],
      topics: ['方案'],
      decisions: ['确认继续推进方案'],
      action_items: ['跟进方案'],
      risks: ['依赖外部资源'],
      keywords: ['方案', '跟进'],
      speaker_stats: [{ speaker: 'SPEAKER_00', segment_count: 1, duration_ms: 2000 }],
      markdown: '# meeting.wav',
      mode: 'local',
      model: null,
      reasoning: null,
    });
    generateMeetingMinutes.mockResolvedValue({
      job_id: 'job-1',
      title: 'meeting.wav',
      summary: 'AI 纪要完成。',
      key_points: ['AI 要点'],
      topics: ['AI 议题'],
      decisions: ['AI 决策'],
      action_items: ['AI 行动项'],
      risks: [],
      keywords: ['AI'],
      speaker_stats: [{ speaker: 'SPEAKER_00', segment_count: 1, duration_ms: 2000 }],
      markdown: '# AI',
      mode: 'llm',
      model: 'MiniMax-M2.7',
      reasoning: '分析转写内容。',
    });
  });

  it('renders standalone minutes and can request AI generation', async () => {
    renderPage();

    expect(await screen.findByText('会议讨论了方案跟进。')).toBeInTheDocument();
    expect(screen.getByText('会议纪要是独立产物，不会污染原文转写视图。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'AI 生成' }));

    await waitFor(() => {
      expect(generateMeetingMinutes).toHaveBeenCalledWith('job-1', true);
    });
    expect(await screen.findByText('AI 纪要完成。')).toBeInTheDocument();
    expect(screen.getByText('AI: MiniMax-M2.7')).toBeInTheDocument();
  });
});
