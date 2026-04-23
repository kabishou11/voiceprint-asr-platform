import { layout, measureLineStats, measureNaturalWidth, prepare, prepareWithSegments, setLocale } from '@chenglou/pretext';
import { Box, Typography, type TypographyProps } from '@mui/material';
import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

type BalancedPretextTextProps = {
  text: string;
  font: string;
  lineHeight: number;
  targetLines?: number;
  minWidth?: number;
  maxWidth?: number;
  typographyProps?: TypographyProps;
};

type MeasuredPretextBlockProps = {
  text: string;
  font: string;
  lineHeight: number;
  typographyProps?: TypographyProps;
};

function canUsePretext() {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return false;
  }
  if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) {
    return false;
  }
  try {
    const canvas = document.createElement('canvas');
    return typeof canvas.getContext === 'function' && canvas.getContext('2d') !== null;
  } catch {
    return false;
  }
}

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') {
      return;
    }

    const update = () => {
      const next = Math.round(element.getBoundingClientRect().width);
      startTransition(() => {
        setWidth(next);
      });
    };

    update();
    const observer = new ResizeObserver(() => update());
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}

function chooseBalancedWidth(params: {
  text: string;
  font: string;
  availableWidth: number;
  lineHeight: number;
  targetLines: number;
  minWidth: number;
  maxWidth?: number;
}) {
  const { text, font, availableWidth, lineHeight, targetLines, minWidth, maxWidth } = params;
  const upper = Math.min(maxWidth ?? availableWidth, availableWidth);
  if (upper <= 0) {
    return null;
  }
  try {
    setLocale('zh-CN');
    const prepared = prepareWithSegments(text, font);
    const naturalWidth = Math.min(Math.ceil(measureNaturalWidth(prepared)), upper);
    const lower = Math.max(Math.min(minWidth, naturalWidth), Math.min(upper, 220));
    let bestWidth = upper;
    let bestScore = Number.POSITIVE_INFINITY;

    for (let width = upper; width >= lower; width -= 12) {
      const { lineCount, maxLineWidth } = measureLineStats(prepared, width);
      const score = Math.abs(lineCount - targetLines) * 1000 + Math.abs(width - maxLineWidth);
      if (score < bestScore) {
        bestScore = score;
        bestWidth = width;
      }
      if (lineCount > targetLines + 1) {
        break;
      }
    }

    const finalWidth = Math.max(lower, Math.min(bestWidth, upper));
    const { lineCount } = measureLineStats(prepared, finalWidth);
    return {
      width: finalWidth,
      lineCount,
      height: lineCount * lineHeight,
    };
  } catch {
    return null;
  }
}

export function BalancedPretextText({
  text,
  font,
  lineHeight,
  targetLines = 2,
  minWidth = 320,
  maxWidth,
  typographyProps,
}: BalancedPretextTextProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const deferredText = useDeferredValue(text);
  const deferredWidth = useDeferredValue(width);

  const result = useMemo(() => {
    if (!canUsePretext() || !deferredText || deferredWidth <= 0) {
      return null;
    }
    return chooseBalancedWidth({
      text: deferredText,
      font,
      availableWidth: deferredWidth,
      lineHeight,
      targetLines,
      minWidth,
      maxWidth,
    });
  }, [deferredText, deferredWidth, font, lineHeight, maxWidth, minWidth, targetLines]);

  return (
    <Box ref={ref} sx={{ width: '100%' }}>
      <Typography
        {...typographyProps}
        sx={{
          ...(typographyProps?.sx ?? {}),
          maxWidth: result ? `${result.width}px` : undefined,
          minHeight: result ? `${result.height}px` : undefined,
          textWrap: 'pretty',
        }}
      >
        {text}
      </Typography>
    </Box>
  );
}

export function MeasuredPretextBlock({
  text,
  font,
  lineHeight,
  typographyProps,
}: MeasuredPretextBlockProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const deferredText = useDeferredValue(text);
  const deferredWidth = useDeferredValue(width);

  const measured = useMemo(() => {
    if (!canUsePretext() || !deferredText || deferredWidth <= 0) {
      return null;
    }
    try {
      setLocale('zh-CN');
      const prepared = prepare(deferredText, font);
      const result = layout(prepared, deferredWidth, lineHeight);
      return result;
    } catch {
      return null;
    }
  }, [deferredText, deferredWidth, font, lineHeight]);

  return (
    <Box ref={ref} sx={{ width: '100%' }}>
      <Typography
        {...typographyProps}
        data-pretext-lines={measured?.lineCount ?? undefined}
        sx={{
          ...(typographyProps?.sx ?? {}),
          minHeight: measured ? `${measured.height}px` : undefined,
          textWrap: 'pretty',
        }}
      >
        {text}
      </Typography>
    </Box>
  );
}
