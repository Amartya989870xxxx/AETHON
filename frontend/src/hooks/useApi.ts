import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  /** True only on the very first load — use to show a skeleton vs. a spinner. */
  initial: boolean;
  refetch: () => void;
}

/**
 * Runs an async fetcher on mount and whenever `deps` change. Aborts the
 * in-flight request on unmount / dep change, keeps the previous data visible
 * while refetching, and exposes a manual `refetch`.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const [initial, setInitial] = useState(true);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(undefined);

    fetcherRef
      .current(ctrl.signal)
      .then((result) => {
        if (ctrl.signal.aborted) return;
        setData(result);
        setInitial(false);
      })
      .catch((err: Error) => {
        if (ctrl.signal.aborted || err.name === "AbortError") return;
        setError(err);
        setInitial(false);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });

    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  return { data, error, loading, initial, refetch };
}
