import { render, screen } from '@testing-library/react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { MemoryRouter } from 'react-router-dom';

import { AppLayout } from './AppLayout';
import { appTheme } from '../theme/appTheme';

describe('AppLayout', () => {
  it('renders product navigation labels', () => {
    render(
      <ThemeProvider theme={appTheme}>
        <CssBaseline />
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByText('智能语音平台')).toBeInTheDocument();
    expect(screen.getAllByText('工作台').length).toBeGreaterThan(0);
    expect(screen.getByText('任务中心')).toBeInTheDocument();
    expect(screen.getAllByText('声纹库').length).toBeGreaterThan(0);
    expect(screen.getByText('模型状态')).toBeInTheDocument();
  });
});
