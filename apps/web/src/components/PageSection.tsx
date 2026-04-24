import { Alert, Box, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import type { ReactNode } from 'react';

interface PageSectionProps {
  title: string;
  description?: string;
  eyebrow?: string;
  eyebrowColor?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'default';
  loading?: boolean;
  error?: string | null;
  actions?: ReactNode;
  compact?: boolean;
  children: ReactNode;
}

export function PageSection({
  title,
  description,
  eyebrow,
  eyebrowColor = 'primary',
  loading,
  error,
  actions,
  compact = false,
  children,
}: PageSectionProps) {
  return (
    <Stack spacing={compact ? 1.6 : 2.2}>
      <Box
        sx={{
          p: compact ? { xs: 1.7, md: 2 } : { xs: 2.1, md: 2.6 },
          borderRadius: compact ? 4 : 5,
          background:
            'linear-gradient(180deg, rgba(255,253,249,0.94) 0%, rgba(255,251,245,0.82) 100%)',
          border: '1px solid',
          borderColor: alpha('#1c2431', 0.06),
          boxShadow: compact ? '0 10px 24px rgba(15,23,42,0.028)' : '0 14px 34px rgba(15,23,42,0.035)',
        }}
      >
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={compact ? 1.4 : 2}
          alignItems={{ xs: 'flex-start', md: 'center' }}
          justifyContent="space-between"
        >
          <Stack spacing={compact ? 0.3 : 0.45}>
            {eyebrow ? (
              <Chip
                size="small"
                label={eyebrow}
                color={eyebrowColor}
                sx={{
                  alignSelf: 'flex-start',
                  fontWeight: 700,
                  fontSize: 12,
                  bgcolor: alpha('#ffffff', 0.72),
                }}
              />
            ) : null}
            <Typography
              variant="h4"
              sx={{
                maxWidth: 760,
                fontSize: compact ? { xs: '1.45rem', md: '1.7rem' } : { xs: '1.8rem', md: '2rem' },
                lineHeight: compact ? 1.12 : 1.08,
              }}
            >
              {title}
            </Typography>
            {description ? (
              <Typography
                color="text.secondary"
                sx={{
                  maxWidth: 760,
                  textWrap: 'pretty',
                  fontSize: compact ? '0.9rem' : '0.95rem',
                  lineHeight: compact ? 1.5 : 1.62,
                }}
              >
                {description}
              </Typography>
            ) : null}
          </Stack>
          {actions}
        </Stack>
      </Box>
      {loading ? <LinearProgress sx={{ borderRadius: 999, height: 6 }} /> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Stack spacing={compact ? 1.8 : 2.2}>{children}</Stack>
    </Stack>
  );
}
