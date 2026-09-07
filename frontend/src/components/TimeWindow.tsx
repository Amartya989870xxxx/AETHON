import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { localInputToUtcParam, utcToLocalInput } from "../lib/datetime";
import { Button, Field, TextInput } from "./controls";

/**
 * A single app-wide time window. `start`/`end` are UTC ISO strings or
 * undefined. Undefined is meaningful: the backend applies its own last-24h
 * default when a param is omitted (`deps.py::time_window`), so the common case
 * sends nothing.
 */
export interface TimeWindowValue {
  start?: string;
  end?: string;
  /** True when neither bound is set (backend default applies). */
  isDefault: boolean;
}

interface TimeWindowContextShape extends TimeWindowValue {
  setWindow: (next: { start?: string; end?: string }) => void;
  reset: () => void;
}

const TimeWindowContext = createContext<TimeWindowContextShape | null>(null);

const PRESETS: { label: string; hours: number }[] = [
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "3d", hours: 72 },
  { label: "7d", hours: 168 },
];

export function TimeWindowProvider({ children }: { children: ReactNode }) {
  const [start, setStart] = useState<string>();
  const [end, setEnd] = useState<string>();

  const setWindow = useCallback((next: { start?: string; end?: string }) => {
    setStart(next.start);
    setEnd(next.end);
  }, []);

  const reset = useCallback(() => {
    setStart(undefined);
    setEnd(undefined);
  }, []);

  const value = useMemo<TimeWindowContextShape>(
    () => ({
      start,
      end,
      isDefault: !start && !end,
      setWindow,
      reset,
    }),
    [start, end, setWindow, reset],
  );

  return (
    <TimeWindowContext.Provider value={value}>
      {children}
    </TimeWindowContext.Provider>
  );
}

export function useTimeWindow(): TimeWindowContextShape {
  const ctx = useContext(TimeWindowContext);
  if (!ctx) throw new Error("useTimeWindow must be used inside TimeWindowProvider");
  return ctx;
}

/** As a plain object for spreading into an endpoint's `query`. */
export function useWindowParams(): { start?: string; end?: string } {
  const { start, end } = useTimeWindow();
  return { start, end };
}

/* -------------------------------------------------------------- the picker */

export function TimeWindowPicker() {
  const { start, end, isDefault, setWindow, reset } = useTimeWindow();
  const [open, setOpen] = useState(false);

  const applyPreset = (hours: number) => {
    const now = new Date();
    const from = new Date(now.getTime() - hours * 3600_000);
    setWindow({ start: from.toISOString(), end: now.toISOString() });
    setOpen(false);
  };

  const label = isDefault
    ? "Last 24h"
    : `${utcToLocalInput(start).replace("T", " ") || "…"} → ${
        utcToLocalInput(end).replace("T", " ") || "now"
      }`;

  return (
    <div className="relative">
      <Button size="sm" onClick={() => setOpen((o) => !o)} icon={<ClockIcon />}>
        {label}
      </Button>

      {open && (
        <div className="glass absolute right-0 z-30 mt-2 w-[19rem] p-4">
          <div className="mb-3 flex gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => applyPreset(p.hours)}
                className="flex-1 rounded-md border border-white/10 bg-white/5 py-1.5 text-xs text-ink-200 transition hover:border-violet-500/40 hover:text-white"
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            <Field label="From (local)">
              <TextInput
                type="datetime-local"
                value={utcToLocalInput(start)}
                onChange={(e) =>
                  setWindow({
                    start: localInputToUtcParam(e.target.value),
                    end,
                  })
                }
              />
            </Field>
            <Field label="To (local)">
              <TextInput
                type="datetime-local"
                value={utcToLocalInput(end)}
                onChange={(e) =>
                  setWindow({
                    start,
                    end: localInputToUtcParam(e.target.value),
                  })
                }
              />
            </Field>
          </div>

          <div className="mt-3 flex justify-between">
            <button
              onClick={() => {
                reset();
                setOpen(false);
              }}
              className="text-xs text-ink-400 transition hover:text-ink-200"
            >
              Reset to 24h default
            </button>
            <button
              onClick={() => setOpen(false)}
              className="text-xs text-violet-400 transition hover:text-violet-300"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ClockIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}
