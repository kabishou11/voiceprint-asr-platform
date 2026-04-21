import { alpha, createTheme } from '@mui/material/styles';

const baseTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2563eb',
      light: '#60a5fa',
      dark: '#1d4ed8',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#0f766e',
      light: '#2dd4bf',
      dark: '#115e59',
    },
    success: {
      main: '#16a34a',
    },
    warning: {
      main: '#f59e0b',
    },
    error: {
      main: '#dc2626',
    },
    background: {
      default: '#f3f6fb',
      paper: '#ffffff',
    },
    text: {
      primary: '#0f172a',
      secondary: '#475569',
    },
    divider: alpha('#0f172a', 0.08),
  },
  shape: {
    borderRadius: 18,
  },
  typography: {
    fontFamily: '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
    h3: {
      fontWeight: 800,
      letterSpacing: '-0.03em',
    },
    h4: {
      fontWeight: 800,
      letterSpacing: '-0.02em',
    },
    h5: {
      fontWeight: 700,
    },
    h6: {
      fontWeight: 700,
    },
    button: {
      fontWeight: 700,
      textTransform: 'none',
    },
  },
});

export const appTheme = createTheme(baseTheme, {
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundImage:
            'radial-gradient(circle at top right, rgba(37,99,235,0.10), transparent 24%), radial-gradient(circle at top left, rgba(15,118,110,0.08), transparent 22%)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background:
            'linear-gradient(180deg, rgba(15,23,42,1) 0%, rgba(15,23,42,0.96) 55%, rgba(30,41,59,0.98) 100%)',
          color: '#e2e8f0',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 24,
          border: `1px solid ${alpha('#0f172a', 0.06)}`,
          boxShadow: '0 18px 48px rgba(15,23,42,0.08)',
          backgroundImage: 'none',
        },
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: {
          borderRadius: 14,
          paddingInline: 18,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          fontWeight: 700,
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        fullWidth: true,
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
  },
});
