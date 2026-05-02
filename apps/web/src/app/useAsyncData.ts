import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

interface PollingOptions<T> {
  enabled?: boolean;
  intervalMs: number;
  stopWhen?: (data: T | null) => boolean;
  pauseWhenHidden?: boolean;
  errorBackoffMs?: number;
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
  const isPollingRefreshRef = useRef(false);
  const inFlightRef = useRef(false);

  useEffect(() => {
    let active = true;
    if (!isPollingRefreshRef.current || data === null) {
      setLoading(true);
    }
    setError(null);
    inFlightRef.current = true;

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
          isPollingRefreshRef.current = false;
          inFlightRef.current = false;
        }
      });

    return () => {
      active = false;
      inFlightRef.current = false;
    };
  }, [...deps, version]);

  useEffect(() => {
    if (!polling?.enabled) {
      return undefined;
    }

    const tick = () => {
      const nextInterval = error && polling.errorBackoffMs ? polling.errorBackoffMs : polling.intervalMs;
      if (polling.pauseWhenHidden && typeof document !== 'undefined' && document.hidden) {
        timeoutRef.current = window.setTimeout(tick, nextInterval);
        return;
      }
      if (polling.stopWhen?.(data ?? null)) {
        return;
      }
      if (inFlightRef.current) {
        timeoutRef.current = window.setTimeout(tick, nextInterval);
        return;
      }
      isPollingRefreshRef.current = true;
      setVersion((current) => current + 1);
      timeoutRef.current = window.setTimeout(tick, nextInterval);
    };

    timeoutRef.current = window.setTimeout(tick, polling.intervalMs);
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, [data, error, polling?.enabled, polling?.intervalMs, polling?.pauseWhenHidden, polling?.stopWhen, polling?.errorBackoffMs]);

  const reload = useCallback(() => {
    isPollingRefreshRef.current = false;
    setVersion((current) => current + 1);
  }, []);

  return { data, loading, error, reload, setData: setData as Dispatch<SetStateAction<T | null>> };
}
