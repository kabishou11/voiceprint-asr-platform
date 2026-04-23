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
  children,
}: PageSectionProps) {
  return (
    <Stack spacing={3}>
      <Box
        sx={{
          p: { xs: 2.6, md: 3.2 },
          borderRadius: 7,
          background:
            'linear-gradient(180deg, rgba(255,253,249,0.94) 0%, rgba(255,251,245,0.82) 100%)',
          border: '1px solid',
          borderColor: alpha('#1c2431', 0.06),
          boxShadow: '0 20px 44px rgba(15,23,42,0.04)',
        }}
      >
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', md: 'center' }}
          justifyContent="space-between"
        >
          <Stack spacing={0.75}>
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
            <Typography variant="h4" sx={{ maxWidth: 760 }}>
              {title}
            </Typography>
            {description ? (
              <Typography
                color="text.secondary"
                sx={{
                  maxWidth: 760,
                  textWrap: 'pretty',
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
      <Stack spacing={3}>{children}</Stack>
    </Stack>
  );
}
