/**
 * The backend hands back plain enum strings with no colour/label metadata, so
 * the visual mapping lives here. Values are copied from the integration guide's
 * enum table and `backend/app/schemas.py`.
 *
 * Colours are hex so they work in Leaflet markers, SVG charts and CSS alike.
 */
import { humanize } from "./format";

export interface EnumStyle {
  label: string;
  /** Foreground / accent colour. */
  color: string;
  /** Translucent background for a badge chip. */
  bg: string;
  border: string;
}

function style(label: string, color: string): EnumStyle {
  return {
    label,
    color,
    bg: `${color}1f`, // ~12% alpha
    border: `${color}59`, // ~35% alpha
  };
}

const NEUTRAL = style("—", "#8b90a0");

// --- severity --------------------------------------------------------

export const SEVERITY_STYLE: Record<string, EnumStyle> = {
  critical: style("Critical", "#fb5b6b"),
  high: style("High", "#ff8f4c"),
  medium: style("Medium", "#ffcc4d"),
  low: style("Low", "#5cd0c0"),
};

// --- alert status ---------------------------------------------------

export const ALERT_STATUS_STYLE: Record<string, EnumStyle> = {
  open: style("Open", "#8b5cf6"),
  acknowledged: style("Acknowledged", "#4ade80"),
  dismissed: style("Dismissed", "#5b6070"),
};

// --- alert type ---------------------------------------------------

export const ALERT_TYPE_STYLE: Record<string, EnumStyle> = {
  blacklist_hit: style("Blacklist Hit", "#fb5b6b"),
  blacklist_possible: style("Blacklist — Possible", "#ff8f4c"),
  impossible_travel: style("Impossible Travel", "#d946ef"),
  restricted_zone: style("Restricted Zone", "#ff8f4c"),
  loitering: style("Loitering", "#ffcc4d"),
  odd_hours: style("Odd Hours", "#5cd0c0"),
};

// --- observation capture condition ------------------------------

export const CONDITION_STYLE: Record<string, EnumStyle> = {
  day_clear: style("Day · Clear", "#5cd0c0"),
  day_rain: style("Day · Rain", "#6bb6ff"),
  night_clear: style("Night · Clear", "#8b5cf6"),
  night_rain: style("Night · Rain", "#a855f7"),
  glare: style("Glare", "#ffcc4d"),
  angled: style("Angled", "#ff8f4c"),
};

// --- trajectory path node match --------------------------------

export const MATCH_STYLE: Record<string, EnumStyle> = {
  exact: style("Exact", "#4ade80"),
};

export function matchStyle(match: string): EnumStyle {
  if (match.startsWith("fuzzy")) return style(humanize(match), "#ffcc4d");
  return MATCH_STYLE[match] ?? NEUTRAL;
}

// --- generic lookup with humanised fallback -------------------

export function lookupStyle(
  table: Record<string, EnumStyle>,
  key: string | null | undefined,
): EnumStyle {
  if (!key) return NEUTRAL;
  return table[key] ?? style(humanize(key), "#8b90a0");
}

/**
 * Congestion score (0..1) -> a colour on a calm→hot ramp, for map markers and
 * the heatmap legend.
 */
export function congestionColor(score: number | null | undefined): string {
  const s = Math.min(1, Math.max(0, score ?? 0));
  const stops: [number, string][] = [
    [0, "#3aa0ff"],
    [0.35, "#5cd0c0"],
    [0.55, "#ffcc4d"],
    [0.75, "#ff8f4c"],
    [1, "#fb5b6b"],
  ];
  for (let i = 1; i < stops.length; i++) {
    const [t1, c1] = stops[i - 1];
    const [t2, c2] = stops[i];
    if (s <= t2) return lerpColor(c1, c2, (s - t1) / (t2 - t1 || 1));
  }
  return stops[stops.length - 1][1];
}

function lerpColor(a: string, b: string, t: number): string {
  const pa = hexToRgb(a);
  const pb = hexToRgb(b);
  const mix = pa.map((v, i) => Math.round(v + (pb[i] - v) * clamp(t)));
  return `#${mix.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function clamp(t: number): number {
  return Math.min(1, Math.max(0, t));
}
