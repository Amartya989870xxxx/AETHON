import { Fragment, type ReactNode } from "react";
import { cx } from "../lib/cx";
import { humanize } from "../lib/format";

/**
 * Renders an arbitrary object as a definition list. Used for alert `evidence`,
 * which is a free-form dict whose shape varies by `alert_type` — the guide is
 * explicit that we must NOT destructure it positionally.
 */
export function KeyValueList({
  data,
  className,
}: {
  data: Record<string, unknown>;
  className?: string;
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-xs text-ink-500">No structured evidence attached.</p>;
  }
  return (
    <dl
      className={cx(
        "grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-2 text-sm",
        className,
      )}
    >
      {entries.map(([key, value]) => (
        <Fragment key={key}>
          <dt className="text-xs text-ink-400">{humanize(key)}</dt>
          <dd className="min-w-0 break-words text-ink-200">
            <Value value={value} />
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

function Value({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-ink-500">—</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span className={value ? "text-signal-ok" : "text-ink-400"}>
        {value ? "yes" : "no"}
      </span>
    );
  }
  if (typeof value === "number" || typeof value === "string") {
    return <span className="tabular-nums">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-500">none</span>;
    if (value.every((v) => typeof v === "string" || typeof v === "number")) {
      return (
        <span className="flex flex-wrap gap-1">
          {value.map((v, i) => (
            <span
              key={i}
              className="rounded bg-white/5 px-1.5 py-0.5 text-xs text-ink-200"
            >
              {String(v)}
            </span>
          ))}
        </span>
      );
    }
  }
  return (
    <pre className="overflow-x-auto rounded bg-ink-900/70 p-2 text-xs text-ink-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
