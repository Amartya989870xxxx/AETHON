import { useEffect, useRef } from "react";

/**
 * Calls `callback` every `delayMs`. Pass `delayMs = null` to pause.
 * The callback ref is kept current so the interval never holds a stale closure.
 */
export function useInterval(callback: () => void, delayMs: number | null): void {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
    if (delayMs === null) return;
    const id = setInterval(() => saved.current(), delayMs);
    return () => clearInterval(id);
  }, [delayMs]);
}
