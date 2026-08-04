import { useState, useEffect, useCallback, useRef } from "react";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, fallback?: T): ApiState<T> {
  const [data, setData] = useState<T | null>(fallback ?? null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const hasData = useRef(false);

  useEffect(() => {
    let cancelled = false;
    // Only show the loading skeleton on the very first fetch.
    // Background refetches update data silently — no blank flash.
    if (!hasData.current) {
      setLoading(true);
    }
    setError(null);
    fetcher()
      .then((result) => {
        if (!cancelled) {
          hasData.current = true;
          setData(result);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          if (fallback !== undefined) {
            setData(fallback);
          }
          setError(err?.message ?? "Request failed");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, refetch };
}
