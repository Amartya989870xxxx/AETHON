import type { ReactNode } from "react";
import { ApiError, NetworkError } from "../api/client";
import { cx } from "../lib/cx";
import { GlassPanel } from "./GlassPanel";

/* ---------------------------------------------------------------- Spinner */

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-ink-500 border-t-accent-500",
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  );
}

/* --------------------------------------------------------------- Skeleton */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        "relative overflow-hidden rounded-md bg-ink-700/50",
        "after:absolute after:inset-0 after:-translate-x-full after:animate-shimmer",
        "after:bg-gradient-to-r after:from-transparent after:via-white/5 after:to-transparent",
        className,
      )}
    />
  );
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- EmptyState */

interface EmptyProps {
  title: string;
  message?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, message, icon, action, className }: EmptyProps) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center gap-2 px-6 py-14 text-center",
        className,
      )}
    >
      {icon && <div className="mb-1 text-ink-500">{icon}</div>}
      <p className="text-sm font-medium text-ink-200">{title}</p>
      {message && (
        <p className="max-w-sm text-xs leading-relaxed text-ink-400">{message}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- ErrorState */

function describe(error: Error): { title: string; message: string } {
  if (error instanceof NetworkError) {
    return { title: "Can't reach the backend", message: error.message };
  }
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return { title: "Not found", message: error.message };
    }
    return { title: `Request failed (${error.status})`, message: error.message };
  }
  return { title: "Something went wrong", message: error.message };
}

interface ErrorProps {
  error: Error;
  onRetry?: () => void;
  /** Render inside a panel (default) or bare. */
  bare?: boolean;
}

export function ErrorState({ error, onRetry, bare }: ErrorProps) {
  const { title, message } = describe(error);
  const body = (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-signal-critical/15 text-signal-critical">
        !
      </div>
      <p className="text-sm font-medium text-ink-100">{title}</p>
      <p className="max-w-md text-xs leading-relaxed text-ink-400">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-ink-200 transition hover:border-accent-500/40 hover:text-white"
        >
          Try again
        </button>
      )}
    </div>
  );
  return bare ? body : <GlassPanel>{body}</GlassPanel>;
}
