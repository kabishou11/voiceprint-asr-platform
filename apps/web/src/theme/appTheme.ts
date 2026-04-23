import { alpha, createTheme } from '@mui/material/styles';

const baseTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2f6fed',
      light: '#6da7ff',
      dark: '#1e4fb8',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#3ab8d9',
      light: '#7dddf0',
      dark: '#1482a0',
    },
    success: {
      main: '#14945a',
    },
    warning: {
      main: '#de9f3c',
    },
    error: {
      main: '#ca5a4d',
    },
    background: {
      default: '#f7f4ee',
      paper: '#fffdf8',
    },
    text: {
      primary: '#1c2431',
      secondary: '#67707c',
    },
    divider: alpha('#1c2431', 0.09),
  },
  shape: {
    borderRadius: 20,
  },
  typography: {
    fontFamily:
      '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Segoe UI", sans-serif',
    h2: {
      fontFamily: '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif',
      fontWeight: 500,
      letterSpacing: '-0.04em',
      lineHeight: 1.04,
    },
    h3: {
      fontFamily: '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif',
      fontWeight: 500,
      letterSpacing: '-0.03em',
      lineHeight: 1.08,
    },
    h4: {
      fontFamily: '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif',
      fontWeight: 500,
      letterSpacing: '-0.025em',
      lineHeight: 1.12,
    },
    h5: {
      fontFamily: '"Iowan Old Style", "Palatino Linotype", "Noto Serif SC", serif',
      fontWeight: 600,
      letterSpacing: '-0.02em',
    },
    h6: {
      fontWeight: 600,
      letterSpacing: '-0.01em',
    },
    subtitle1: {
      fontWeight: 600,
    },
    body1: {
      lineHeight: 1.75,
    },
    body2: {
      lineHeight: 1.7,
    },
    button: {
      fontWeight: 600,
      textTransform: 'none',
      letterSpacing: '-0.01em',
    },
  },
});

export const appTheme = createTheme(baseTheme, {
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        ':root': {
          colorScheme: 'light',
        },
        body: {
          backgroundColor: '#f7f4ee',
          backgroundImage: [
            'radial-gradient(circle at top left, rgba(47,111,237,0.07), transparent 20%)',
            'radial-gradient(circle at 78% 18%, rgba(58,184,217,0.08), transparent 17%)',
            'linear-gradient(180deg, rgba(255,255,255,0.74) 0%, rgba(247,244,238,0.94) 100%)',
          ].join(','),
        },
        '*::-webkit-scrollbar': {
          width: 10,
          height: 10,
        },
        '*::-webkit-scrollbar-thumb': {
          backgroundColor: alpha('#8a939f', 0.28),
          borderRadius: 999,
          border: '2px solid transparent',
          backgroundClip: 'padding-box',
        },
        '*::-webkit-scrollbar-track': {
          backgroundColor: 'transparent',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background: 'rgba(250,248,243,0.9)',
          backdropFilter: 'blur(24px)',
          color: '#1c2431',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 28,
          border: `1px solid ${alpha('#1c2431', 0.08)}`,
          boxShadow: '0 18px 54px rgba(28,36,49,0.045)',
          backgroundImage: 'none',
          backgroundColor: alpha('#fffdf9', 0.95),
        },
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: {
          borderRadius: 16,
          paddingInline: 18,
          minHeight: 42,
          boxShadow: 'none',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          fontWeight: 600,
        },
      },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          borderRadius: 24,
          overflow: 'hidden',
          '&:before': {
            display: 'none',
          },
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        fullWidth: true,
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 20,
          backgroundColor: alpha('#ffffff', 0.82),
          '& fieldset': {
            borderColor: alpha('#1c2431', 0.1),
          },
          '&:hover fieldset': {
            borderColor: alpha('#1c2431', 0.18),
          },
        },
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
