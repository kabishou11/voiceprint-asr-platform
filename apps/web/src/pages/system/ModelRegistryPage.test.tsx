import { render, screen, waitFor } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { ModelRegistryPage } from './ModelRegistryPage';
import { appTheme } from '../../theme/appTheme';

const fetchModels = vi.fn();

vi.mock('../../api/client', () => ({
  fetchModels: () => fetchModels(),
}));

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <MemoryRouter>
        <ModelRegistryPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('ModelRegistryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchModels.mockResolvedValue({
      items: [
        {
          key: 'funasr-nano',
          display_name: 'FunASR Nano',
          task: 'transcription',
          provider: 'funasr',
          availability: 'available',
          experimental: false,
        },
        {
          key: '3dspeaker-diarization',
          display_name: '3D-Speaker Diarization',
          task: 'diarization',
          provider: '3dspeaker',
          availability: 'available',
          experimental: false,
        },
        {
          key: '3dspeaker-embedding',
          display_name: '3D-Speaker Voiceprint',
          task: 'voiceprint',
          provider: '3dspeaker',
          availability: 'available',
          experimental: false,
        },
        {
          key: 'pyannote-community-1',
          display_name: 'pyannote Community-1',
          task: 'diarization',
          provider: 'pyannote',
          availability: 'unavailable',
          experimental: false,
        },
      ],
    });
  });

  it('explains the current local model state and gated pyannote limitation', async () => {
    renderPage();

    await waitFor(() => {
      expect(fetchModels).toHaveBeenCalled();
    });

    expect(await screen.findByText(/3D-Speaker 本地模型已就绪/)).toBeInTheDocument();
    expect(screen.getByText(/已识别到 CUDA GPU/)).toBeInTheDocument();
    expect(screen.getByText(/gated repo/)).toBeInTheDocument();
    expect(screen.getByText(/不会启用/)).toBeInTheDocument();
  });
});
