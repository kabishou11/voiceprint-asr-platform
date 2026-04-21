import { Alert, Box, LinearProgress, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

interface PageSectionProps {
  title: string;
  description?: string;
  loading?: boolean;
  error?: string | null;
  actions?: ReactNode;
  children: ReactNode;
}

export function PageSection({ title, description, loading, error, actions, children }: PageSectionProps) {
  return (
    <Stack spacing={3}>
      <Box
        sx={{
          p: { xs: 2.5, md: 3 },
          borderRadius: 6,
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
          boxShadow: '0 16px 40px rgba(15,23,42,0.06)',
        }}
      >
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', md: 'center' }}
          justifyContent="space-between"
        >
          <Stack spacing={0.75}>
            <Typography variant="h4">{title}</Typography>
            {description ? (
              <Typography color="text.secondary" sx={{ maxWidth: 720 }}>
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
