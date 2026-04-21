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
  const foreground = light ? '#f8fafc' : '#0f172a';

  return (
    <Box
      sx={{
        width: size,
        height: size,
        position: 'relative',
        borderRadius: `${Math.max(18, Math.round(size * 0.28))}px`,
        overflow: 'hidden',
        background:
          'radial-gradient(circle at 28% 24%, rgba(255,255,255,0.42), transparent 30%), linear-gradient(135deg, #2563eb 0%, #1d4ed8 44%, #0f766e 100%)',
        boxShadow: light ? '0 18px 48px rgba(15,23,42,0.28)' : '0 18px 40px rgba(37,99,235,0.24)',
        border: `1px solid ${alpha('#ffffff', light ? 0.32 : 0.18)}`,
      }}
    >
      <Box
        sx={{
          position: 'absolute',
          inset: '12%',
          borderRadius: '50%',
          border: `1px solid ${alpha('#ffffff', 0.22)}`,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          inset: '24%',
          borderRadius: '50%',
          border: `1px solid ${alpha('#ffffff', 0.3)}`,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          inset: '36%',
          borderRadius: '50%',
          bgcolor: alpha('#ffffff', 0.18),
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: `1px solid ${alpha('#ffffff', 0.28)}`,
        }}
      >
        <Typography
          sx={{
            fontSize: Math.max(10, Math.round(size * 0.2)),
            lineHeight: 1,
            fontWeight: 900,
            letterSpacing: '0.08em',
            color: '#ffffff',
            ml: '0.08em',
          }}
        >
          VP
        </Typography>
      </Box>
      {[0, 1, 2].map((item) => (
        <Box
          key={`left-${item}`}
          sx={{
            position: 'absolute',
            left: `${15 + item * 5}%`,
            bottom: `${18 + item * 8}%`,
            width: '6%',
            height: `${18 + item * 11}%`,
            borderRadius: 999,
            bgcolor: alpha('#ffffff', 0.82 - item * 0.12),
          }}
        />
      ))}
      {[0, 1, 2].map((item) => (
        <Box
          key={`right-${item}`}
          sx={{
            position: 'absolute',
            right: `${15 + item * 5}%`,
            top: `${18 + item * 8}%`,
            width: '6%',
            height: `${18 + item * 11}%`,
            borderRadius: 999,
            bgcolor: alpha('#ffffff', 0.82 - item * 0.12),
          }}
        />
      ))}
      <Box
        sx={{
          position: 'absolute',
          right: '14%',
          bottom: '14%',
          width: '16%',
          height: '16%',
          borderRadius: '50%',
          bgcolor: alpha('#99f6e4', 0.92),
          boxShadow: '0 0 0 4px rgba(255,255,255,0.12)',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          borderRadius: 'inherit',
          border: `1px solid ${alpha(foreground, light ? 0 : 0.05)}`,
          pointerEvents: 'none',
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
