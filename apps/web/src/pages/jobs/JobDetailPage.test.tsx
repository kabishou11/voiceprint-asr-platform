import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import { buildJobExportDocument, JobDetailPage } from './JobDetailPage';
import { appTheme } from '../../theme/appTheme';

const fetchTranscript = vi.fn();
const fetchMeetingMinutes = vi.fn();

vi.mock('../../api/client', () => ({
  fetchTranscript: (...args: unknown[]) => fetchTranscript(...args),
  fetchMeetingMinutes: (...args: unknown[]) => fetchMeetingMinutes(...args),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname + location.search}</div>;
}

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter initialEntries={['/jobs/job-1']}>
        <Routes>
          <Route path="/" element={<LocationProbe />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/minutes/:jobId" element={<LocationProbe />} />
          <Route path="/voiceprints" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('JobDetailPage', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
    fetchTranscript.mockResolvedValue({
      job: {
        job_id: 'job-1',
        job_type: 'multi_speaker_transcription',
        status: 'succeeded',
        created_at: '2026-04-21T10:00:00Z',
        updated_at: '2026-04-21T10:02:00Z',
        asset_name: 'meeting.wav',
        error_message: null,
      },
      transcript: {
        text: '你好。我们开始开会。',
        language: 'zh-cn',
        metadata: {
          alignment_source: 'exclusive',
          timelines: [
            { label: 'Regular diarization', source: 'regular', segments: [{ start_ms: 0, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
            { label: 'Exclusive alignment timeline', source: 'exclusive', segments: [{ start_ms: 0, end_ms: 2000, text: '', speaker: null }, { start_ms: 2000, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
            { label: 'Display speaker timeline', source: 'display', segments: [{ start_ms: 0, end_ms: 2500, text: '', speaker: null }, { start_ms: 2500, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
          ],
          diarization_model: '3dspeaker-diarization',
        },
        segments: [
          { start_ms: 0, end_ms: 2000, text: '你好。', speaker: null, confidence: 0.71 },
          { start_ms: 2000, end_ms: 8000, text: '我们开始开会。', speaker: 'SPEAKER_00', confidence: 0.93 },
        ],
      },
    });
    fetchMeetingMinutes.mockResolvedValue({
      job_id: 'job-1',
      title: 'meeting.wav',
      summary: 'SPEAKER_00: 我们开始开会。',
      key_points: ['SPEAKER_00: 我们开始开会。'],
      topics: ['我们开始开会。'],
      decisions: ['SPEAKER_00: 确认我们开始开会。'],
      action_items: ['SPEAKER_00: 我们开始开会。'],
      risks: [],
      keywords: ['开会'],
      speaker_stats: [{ speaker: 'SPEAKER_00', segment_count: 1, duration_ms: 6000 }],
      markdown: '# meeting.wav\n\n## 摘要\nSPEAKER_00: 我们开始开会。',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('groups speakers and navigates to voiceprint page with context', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchTranscript).toHaveBeenCalledWith('job-1');
    });

    expect(screen.getAllByText('Speaker 2').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '会议纪要' })).toBeInTheDocument();
    const buttons = await screen.findAllByRole('button', { name: '对这个 Speaker 做声纹处理' });
    fireEvent.click(buttons[0]);

    expect(await screen.findByTestId('location-probe')).toHaveTextContent(
      '/voiceprints?probe=meeting.wav&speaker=SPEAKER_00&jobId=job-1',
    );
  });

  it('loads speaker alias from local storage and supports quick retry', async () => {
    window.localStorage.setItem(
      'voiceprint-job-speaker-mappings',
      JSON.stringify({
        'job-1': {
          SPEAKER_00: '张三',
        },
      }),
    );

    renderPage();

    expect((await screen.findAllByText('张三')).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: '快速重跑' }));

    await waitFor(() => {
      const probes = screen.getAllByTestId('location-probe');
      expect(probes.at(-1)).toHaveTextContent('/?asset=meeting.wav&language=zh-cn&mode=multi');
    });
  });

  it('supports filtering segments by speaker in review workspace', async () => {
    renderPage();

    expect((await screen.findAllByText('Speaker 2')).length).toBeGreaterThan(0);
    expect(screen.queryByText('未标注说话人')).not.toBeInTheDocument();
    expect(screen.getByText('Exclusive')).toBeInTheDocument();
    expect(screen.getByText('exclusive 2 段')).toBeInTheDocument();
    expect(screen.getByText('display 2 段')).toBeInTheDocument();
    expect(screen.getAllByTestId('speaker-timeline-row')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 2 · 1 段' }));

    expect((await screen.findAllByText('Speaker 2')).length).toBeGreaterThan(0);
    expect(screen.getByText(/Speaker 2 · 6\.0 秒 · 1 段/)).toBeInTheDocument();
    expect(screen.getAllByText('我们开始开会。').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('speaker-timeline-row')).toHaveLength(1);
    expect(screen.getAllByText('2000ms - 8000ms').length).toBeGreaterThan(0);
  });

  it('exports filtered speaker payload when a speaker is selected', async () => {
    const createObjectURL = vi.fn(() => 'blob:job-1');
    const revokeObjectURL = vi.fn(() => undefined);
    Object.defineProperty(window.URL, 'createObjectURL', {
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      writable: true,
      value: revokeObjectURL,
    });
    const anchorClick = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'a') {
        return {
          href: '',
          download: '',
          click: anchorClick,
        } as unknown as HTMLAnchorElement;
      }
      return originalCreateElement(tagName);
    }) as typeof document.createElement);

    renderPage();

    expect((await screen.findAllByText('Speaker 2')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 2 · 1 段' }));
    fireEvent.click(screen.getByRole('button', { name: '导出当前 Speaker JSON' }));

    const payload = buildJobExportDocument({
      job: {
        job_id: 'job-1',
      },
      transcript: {
        text: '你好。我们开始开会。',
        metadata: {
          alignment_source: 'exclusive',
          timelines: [
            { label: 'Regular diarization', source: 'regular', segments: [{ start_ms: 0, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
            { label: 'Exclusive alignment timeline', source: 'exclusive', segments: [{ start_ms: 2000, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
            { label: 'Display speaker timeline', source: 'display', segments: [{ start_ms: 2000, end_ms: 8000, text: '', speaker: 'SPEAKER_00' }] },
          ],
          diarization_model: '3dspeaker-diarization',
        },
        segments: [
          { start_ms: 0, end_ms: 2000, text: '你好。', speaker: 'SPEAKER_01', confidence: 0.71 },
          { start_ms: 2000, end_ms: 8000, text: '我们开始开会。', speaker: 'SPEAKER_00', confidence: 0.93 },
        ],
      },
      filteredSegments: [
        { start_ms: 2000, end_ms: 8000, text: '我们开始开会。', speaker: 'SPEAKER_00', confidence: 0.93 },
      ],
      selectedSpeakerGroup: {
        speaker: 'SPEAKER_00',
        displaySpeaker: 'SPEAKER_00',
        durationMs: 6000,
        segments: [
          { start_ms: 2000, end_ms: 8000, text: '我们开始开会。', speaker: 'SPEAKER_00', confidence: 0.93 },
        ],
      },
      speakerAliases: {},
    });

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(payload.speaker_focus).toMatchObject({
      speaker: 'SPEAKER_00',
      display_name: 'SPEAKER_00',
      segment_count: 1,
    });
    expect(payload.timeline_metadata).toMatchObject({
      alignment_source: 'exclusive',
      diarization_model: '3dspeaker-diarization',
    });
    expect(payload.transcript).not.toBeNull();
    expect(payload.transcript!.segments).toEqual([
      { start_ms: 2000, end_ms: 8000, text: '我们开始开会。', speaker: 'SPEAKER_00', confidence: 0.93 },
    ]);
    expect(payload.transcript!.text).toBe('我们开始开会。');
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:job-1');
    createElement.mockRestore();
  });
});
