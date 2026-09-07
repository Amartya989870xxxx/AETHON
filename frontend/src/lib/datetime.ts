/**
 * Every timestamp AETHON accepts or returns is UTC. Some fields (written by
 * SQLite) come back with no offset suffix at all — those are STILL UTC, not
 * local. These helpers are the only place the app parses or formats a
 * timestamp; components never call `new Date(x).toString()` directly.
 */

/** ISO string with no timezone designator -> treat as UTC by appending `Z`. */
export function normalizeIso(iso: string): string {
  const trimmed = iso.trim();
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(trimmed);
  return hasZone ? trimmed : `${trimmed}Z`;
}

/** Parse an API timestamp to a Date, honouring the "no suffix means UTC" rule. */
export function parseUtc(iso: string): Date {
  return new Date(normalizeIso(iso));
}

const DATE_TIME: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
};

/** UTC timestamp -> the viewer's local time, formatted for display. */
export function formatLocal(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = DATE_TIME,
): string {
  if (!iso) return "—";
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, opts).format(d);
}

/** Just the local clock time (HH:MM), for dense feeds. */
export function formatLocalTime(iso: string | null | undefined): string {
  return formatLocal(iso, { hour: "2-digit", minute: "2-digit" });
}

/** "3 min ago" / "in 2 h" style relative label. */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const deltaSec = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(deltaSec);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < 60) return rtf.format(Math.round(deltaSec), "second");
  if (abs < 3600) return rtf.format(Math.round(deltaSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(deltaSec / 3600), "hour");
  return rtf.format(Math.round(deltaSec / 86400), "day");
}

/**
 * A `<input type="datetime-local">` value is in the viewer's local zone.
 * Convert it to a UTC ISO string for a query param. Empty -> undefined so the
 * caller can lean on the server-side 24h default.
 */
export function localInputToUtcParam(value: string): string | undefined {
  if (!value) return undefined;
  const d = new Date(value); // interpreted as local time
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

/** UTC ISO string -> a value suitable for `<input type="datetime-local">`. */
export function utcToLocalInput(iso: string | undefined): string {
  if (!iso) return "";
  const d = parseUtc(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/** Duration in seconds -> "17m 52s" / "1h 04m". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rem = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(rem).padStart(2, "0")}s`;
  return `${rem}s`;
}
