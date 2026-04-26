import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

interface PollingOptions<T> {
  enabled?: boolean;
  intervalMs: number;
  stopWhen?: (data: T | null) => boolean;
  pauseWhenHidden?: boolean;
}

export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  polling?: PollingOptions<T>,
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    loader()
      .then((result) => {
        if (active) {
          setData(result);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : '加载失败');
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [...deps, version]);

  useEffect(() => {
    if (!polling?.enabled) {
      return undefined;
    }

    const tick = () => {
      if (polling.pauseWhenHidden && typeof document !== 'undefined' && document.hidden) {
        timeoutRef.current = window.setTimeout(tick, polling.intervalMs);
        return;
      }
      if (polling.stopWhen?.(data ?? null)) {
        return;
      }
      setVersion((current) => current + 1);
      timeoutRef.current = window.setTimeout(tick, polling.intervalMs);
    };

    timeoutRef.current = window.setTimeout(tick, polling.intervalMs);
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, [data, polling?.enabled, polling?.intervalMs, polling?.pauseWhenHidden, polling?.stopWhen]);

  const reload = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);

  return { data, loading, error, reload, setData: setData as Dispatch<SetStateAction<T | null>> };
}
