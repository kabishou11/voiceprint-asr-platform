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
      <CardContent sx={{ py: 1.4, px: 1.6, '&:last-child': { pb: 1.4 } }}>
        <Stack direction="row" spacing={1.2} alignItems="center">
          {icon ? (
            <Box
              sx={{
                width: 34,
                height: 34,
                borderRadius: 2.5,
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
            <Typography color="text.secondary" variant="body2" sx={{ fontSize: '0.82rem', lineHeight: 1.3 }}>
              {label}
            </Typography>
            <Typography variant="h6" sx={{ fontSize: '1.05rem', lineHeight: 1.2 }}>{value}</Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
