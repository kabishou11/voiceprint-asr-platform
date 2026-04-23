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
  const bg = 'linear-gradient(155deg, #1d4ed8 0%, #2563eb 58%, #14b8c8 100%)';

  return (
    <Box
      sx={{
        width: size,
        height: size,
        position: 'relative',
        borderRadius: `${Math.max(16, Math.round(size * 0.24))}px`,
        overflow: 'hidden',
        background: bg,
        boxShadow: light
          ? '0 18px 42px rgba(7,24,68,0.24)'
          : '0 16px 36px rgba(47,111,237,0.18)',
        border: `1px solid ${alpha('#ffffff', light ? 0.3 : 0.2)}`,
        flexShrink: 0,
        '&::after': {
          content: '""',
          position: 'absolute',
          inset: '6%',
          borderRadius: 'inherit',
          border: `1px solid ${alpha('#e0f2fe', 0.45)}`,
          opacity: 0.9,
        },
      }}
    >
      {/* Outer arcs - left */}
      <Box
        sx={{
          position: 'absolute',
          top: `${size * 0.12}px`,
          left: `${size * 0.18}px`,
          width: `${size * 0.31}px`,
          height: `${size * 0.31}px`,
          borderRadius: '50%',
          border: `${size * 0.038}px solid ${alpha('#bfdbfe', 0.78)}`,
          borderRightColor: 'transparent',
          borderBottomColor: 'transparent',
          transform: 'rotate(-45deg)',
        }}
      />
      {/* Outer arcs - right */}
      <Box
        sx={{
          position: 'absolute',
          top: `${size * 0.12}px`,
          right: `${size * 0.18}px`,
          width: `${size * 0.31}px`,
          height: `${size * 0.31}px`,
          borderRadius: '50%',
          border: `${size * 0.038}px solid ${alpha('#93c5fd', 0.74)}`,
          borderLeftColor: 'transparent',
          borderBottomColor: 'transparent',
          transform: 'rotate(45deg)',
        }}
      />
      {/* Waveform bars left (ascending) */}
      {[0, 1, 2].map((i) => (
        <Box
          key={`wl-${i}`}
          sx={{
            position: 'absolute',
            bottom: `${size * 0.18}px`,
            left: `${size * (0.14 + i * 0.072)}px`,
            width: `${size * 0.055}px`,
            height: `${size * (0.078 + i * 0.06)}px`,
            borderRadius: 999,
            bgcolor: alpha('#67e8f9', 0.92 - i * 0.12),
          }}
        />
      ))}
      {/* Waveform bars right (ascending) */}
      {[0, 1, 2].map((i) => (
        <Box
          key={`wr-${i}`}
          sx={{
            position: 'absolute',
            bottom: `${size * 0.18}px`,
            right: `${size * (0.14 + i * 0.072)}px`,
            width: `${size * 0.055}px`,
            height: `${size * (0.078 + i * 0.06)}px`,
            borderRadius: 999,
            bgcolor: alpha('#67e8f9', 0.92 - i * 0.12),
          }}
        />
      ))}
      {/* Center pulse dot */}
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: `${size * 0.22}px`,
          height: `${size * 0.22}px`,
          borderRadius: '50%',
          bgcolor: 'rgba(255,255,255,0.95)',
          boxShadow: '0 0 24px rgba(255,255,255,0.45)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Box
          sx={{
            width: `${size * 0.1}px`,
            height: `${size * 0.1}px`,
            borderRadius: '50%',
            bgcolor: '#22d3ee',
            boxShadow: '0 0 18px rgba(34,211,238,0.72)',
          }}
        />
      </Box>
      {/* Teal accent dot */}
      <Box
        sx={{
          position: 'absolute',
          right: `${size * 0.1}px`,
          bottom: `${size * 0.1}px`,
          width: `${size * 0.09}px`,
          height: `${size * 0.09}px`,
          borderRadius: '50%',
          bgcolor: alpha('#5eead4', 0.92),
          boxShadow: '0 0 18px rgba(94,234,212,0.55)',
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
