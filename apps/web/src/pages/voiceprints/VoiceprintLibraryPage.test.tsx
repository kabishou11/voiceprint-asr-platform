import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { VoiceprintLibraryPage } from './VoiceprintLibraryPage';
import { appTheme } from '../../theme/appTheme';

const fetchVoiceprintProfiles = vi.fn();
const createVoiceprintProfile = vi.fn();
const uploadAudio = vi.fn();
const enrollVoiceprint = vi.fn();
const verifyVoiceprint = vi.fn();
const identifyVoiceprint = vi.fn();

vi.mock('../../api/client', () => ({
  fetchVoiceprintProfiles: () => fetchVoiceprintProfiles(),
  createVoiceprintProfile: (...args: unknown[]) => createVoiceprintProfile(...args),
  uploadAudio: (...args: unknown[]) => uploadAudio(...args),
  enrollVoiceprint: (...args: unknown[]) => enrollVoiceprint(...args),
  verifyVoiceprint: (...args: unknown[]) => verifyVoiceprint(...args),
  identifyVoiceprint: (...args: unknown[]) => identifyVoiceprint(...args),
}));

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter>
        <VoiceprintLibraryPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('VoiceprintLibraryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchVoiceprintProfiles.mockResolvedValue({
      items: [
        {
          profile_id: 'sample-female-1',
          display_name: '女声样本 1',
          model_key: '3dspeaker-embedding',
          sample_count: 1,
        },
      ],
    });
    createVoiceprintProfile.mockResolvedValue({
      profile: {
        profile_id: 'profile-2',
        display_name: '测试用户',
        model_key: '3dspeaker-embedding',
        sample_count: 0,
      },
    });
    uploadAudio.mockResolvedValue({
      asset_name: 'uploaded.wav',
      original_filename: 'voice.wav',
      size: 123,
    });
    enrollVoiceprint.mockResolvedValue({
      profile: {
        profile_id: 'sample-female-1',
        display_name: '女声样本 1',
        model_key: '3dspeaker-embedding',
        sample_count: 1,
      },
      enrollment: {
        profile_id: 'sample-female-1',
        asset_name: 'uploaded.wav',
        status: 'enrolled',
        mode: 'replace',
      },
    });
    verifyVoiceprint.mockResolvedValue({
      result: {
        profile_id: 'sample-female-1',
        score: 0.98,
        threshold: 0.7,
        matched: true,
      },
    });
    identifyVoiceprint.mockResolvedValue({
      result: {
        matched: true,
        candidates: [
          { profile_id: 'sample-female-1', display_name: '女声样本 1', score: 0.98, rank: 1 },
        ],
      },
    });
  });

  it('creates profile from dialog', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchVoiceprintProfiles).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole('button', { name: '新建档案' }));
    fireEvent.change(screen.getByLabelText('档案名称'), { target: { value: '测试用户' } });
    fireEvent.click(screen.getByRole('button', { name: '创建' }));

    await waitFor(() => {
      expect(createVoiceprintProfile).toHaveBeenCalledWith('测试用户', '3dspeaker-embedding');
    });
    expect((await screen.findAllByText('测试用户')).length).toBeGreaterThan(0);
  });

  it('uploads and enrolls voiceprint sample', async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(fetchVoiceprintProfiles).toHaveBeenCalled();
    });

    const fileInputs = container.querySelectorAll('input[type="file"]');
    const file = new File(['voice'], 'voice.wav', { type: 'audio/wav' });
    fireEvent.change(fileInputs[0] as HTMLInputElement, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '开始注册' }));

    await waitFor(() => {
      expect(uploadAudio).toHaveBeenCalled();
      expect(enrollVoiceprint).toHaveBeenCalledWith('sample-female-1', 'uploaded.wav');
    });
    expect(await screen.findByText(/注册完成/)).toBeInTheDocument();
  });

  it('uploads probe and calls verify / identify', async () => {
    const { container } = renderPage();

    await waitFor(() => {
      expect(fetchVoiceprintProfiles).toHaveBeenCalled();
    });

    const fileInputs = container.querySelectorAll('input[type="file"]');
    const file = new File(['probe'], 'probe.wav', { type: 'audio/wav' });

    fireEvent.change(fileInputs[1] as HTMLInputElement, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '开始验证' }));

    await waitFor(() => {
      expect(verifyVoiceprint).toHaveBeenCalledWith('sample-female-1', 'uploaded.wav', 0.7);
    });
    expect(await screen.findByText(/相似度 0.98/)).toBeInTheDocument();

    fireEvent.change(fileInputs[1] as HTMLInputElement, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '开始识别' }));

    await waitFor(() => {
      expect(identifyVoiceprint).toHaveBeenCalledWith('uploaded.wav', 3);
    });
    expect(await screen.findByText(/1\. 女声样本 1 · 相似度 0.98/)).toBeInTheDocument();
  });
});
