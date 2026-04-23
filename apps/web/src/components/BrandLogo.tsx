import { Box, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';

interface BrandLogoProps {
  size?: number;
  title?: string;
  subtitle?: string;
  withWordmark?: boolean;
  light?: boolean;
}

function BrandMark({ size = 52, light = false }: Pick<BrandLogoProps, 'size' | 'light'>) {
  return (
    <Box
      sx={{
        width: size,
        height: size,
        borderRadius: `${Math.max(16, Math.round(size * 0.24))}px`,
        overflow: 'hidden',
        boxShadow: light
          ? '0 18px 42px rgba(7,24,68,0.24)'
          : '0 16px 36px rgba(47,111,237,0.18)',
        border: `1px solid ${alpha('#ffffff', light ? 0.3 : 0.18)}`,
        flexShrink: 0,
      }}
    >
      <Box
        component="img"
        src="/logo.svg"
        alt="Voiceprint ASR Platform"
        sx={{
          display: 'block',
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          filter: light ? 'brightness(1.02) saturate(1.02)' : 'none',
        }}
      />
    </Box>
  );
}

export function BrandLogo({
  size = 52,
  title = '智能语音平台',
  subtitle = '多人转写 · 说话人分离 · 声纹核验',
  withWordmark = true,
  light = false,
}: BrandLogoProps) {
  if (!withWordmark) {
    return <BrandMark size={size} light={light} />;
  }

  return (
    <Stack direction="row" spacing={1.5} alignItems="center">
      <BrandMark size={size} light={light} />
      <Box>
        <Typography
          variant="h6"
          sx={{
            color: light ? '#f8fafc' : 'text.primary',
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            fontWeight: 600,
          }}
        >
          {title}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            color: light ? alpha('#e2e8f0', 0.82) : 'text.secondary',
            mt: 0.5,
          }}
        >
          {subtitle}
        </Typography>
      </Box>
    </Stack>
  );
}
