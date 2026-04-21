import type { SxProps, Theme } from '@mui/material';
import { Box, Card, CardContent, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: ReactNode;
  color?: 'primary' | 'success' | 'error' | 'warning';
  sx?: SxProps<Theme>;
}

export function StatCard({ label, value, icon, color = 'primary', sx }: StatCardProps) {
  return (
    <Card sx={sx}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center">
          {icon ? (
            <Box
              sx={{
                width: 40,
                height: 40,
                borderRadius: 3,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: `${color}.main`,
                color: '#fff',
                opacity: 0.9,
                flexShrink: 0,
              }}
            >
              {icon}
            </Box>
          ) : null}
          <Box>
            <Typography color="text.secondary" variant="body2">
              {label}
            </Typography>
            <Typography variant="h5">{value}</Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
