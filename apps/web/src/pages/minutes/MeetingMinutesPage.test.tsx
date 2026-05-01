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
      evidence: {
        decisions: [
          {
            item: '确认继续推进方案',
            evidence_score: 0.82,
            reason: '转写中明确提到继续推进方案。',
            speaker: 'SPEAKER_00',
            start_ms: 0,
            end_ms: 2000,
          },
        ],
        action_items: [
          {
            item: '跟进方案',
            evidence_score: 0.28,
            reason: '行动责任人不明确。',
            speaker: 'SPEAKER_00',
            start_ms: 0,
            end_ms: 2000,
          },
        ],
      },
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
      evidence: {
        decisions: [
          {
            item: 'AI 决策',
            evidence_score: 0.91,
            reason: '模型从转写内容中找到明确决策表述。',
            speaker: 'SPEAKER_00',
            start_ms: 0,
            end_ms: 2000,
          },
        ],
      },
    });
  });

  it('renders standalone minutes and can request AI generation', async () => {
    renderPage();

    expect(await screen.findByText('会议讨论了方案跟进。')).toBeInTheDocument();
    expect(screen.getByText('会议纪要是独立产物，不会污染原文转写视图。')).toBeInTheDocument();
    expect(screen.getByText('证据覆盖')).toBeInTheDocument();
    expect(screen.getByText('已关联 2 条证据，1 条低证据需要复核。')).toBeInTheDocument();
    expect(screen.getByText('无 reasoning')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'AI 生成' }));

    await waitFor(() => {
      expect(generateMeetingMinutes).toHaveBeenCalledWith('job-1', true);
    });
    expect(await screen.findByText('AI 纪要完成。')).toBeInTheDocument();
    expect(screen.getByText('模型生成 · MiniMax-M2.7')).toBeInTheDocument();
    expect(screen.getByText('reasoning 已返回')).toBeInTheDocument();
    expect(screen.getByText('已关联 1 条证据，当前证据可信度良好。')).toBeInTheDocument();
    fireEvent.click(screen.getByText('模型思考'));
    expect(screen.getByText('分析转写内容。')).toBeInTheDocument();
  });
});
