/**
 * Small display formatters. The important one is `nullable`: several numeric
 * fields (`avg_speed_kmph`, `z_score`, `density_per_lane`, ...) are legitimately
 * `null` — a bucket with no speed-capable reads, a segment with too little
 * history for a baseline. The UI must show a real empty state, never `NaN`.
 */

/** 0..1 confidence/score -> "94%". Never assume the API pre-multiplied. */
export function pct(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 0..1 -> a 0..1 clamped number, for widths / opacities. */
export function clamp01(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

/** Render a nullable value, or a labelled fallback for the null case. */
export function nullable<T>(
  value: T | null | undefined,
  render: (v: T) => string,
  fallback = "not enough history yet",
): string {
  if (value == null) return fallback;
  return render(value);
}

/** A nullable number with fixed decimals and an optional unit suffix. */
export function num(
  value: number | null | undefined,
  opts: { digits?: number; unit?: string; fallback?: string } = {},
): string {
  const { digits = 1, unit = "", fallback = "—" } = opts;
  if (value == null || Number.isNaN(value)) return fallback;
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

/** Compact integer with thousands separators. */
export function count(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat().format(value);
}

/** Title-case a snake_case / kebab enum string for display. */
export function humanize(token: string): string {
  return token
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** km distance -> "9.63 km" / "820 m". */
export function distanceKm(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (value < 1) return `${Math.round(value * 1000)} m`;
  return `${value.toFixed(2)} km`;
}
