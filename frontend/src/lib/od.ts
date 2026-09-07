/**
 * Helpers for the origin-destination matrix (`GET /api/analytics/od`).
 *
 * The response is a nested object, NOT a flat edge list:
 *   { zones: [...], matrix: { origin: { dest: count } }, avg_duration_s: {...} }
 * `matrix[origin][dest]`; the diagonal is always 0 by construction (intra-zone
 * trips are excluded, not merely zero).
 */
import type { ODMatrix } from "../api/types";

export interface ODCell {
  origin: string;
  dest: string;
  count: number;
  avgDurationS: number | null;
  isDiagonal: boolean;
}

/** Every cell of the zones × zones grid, row-major, ready to render. */
export function odCells(od: ODMatrix): ODCell[] {
  const cells: ODCell[] = [];
  for (const origin of od.zones) {
    for (const dest of od.zones) {
      cells.push({
        origin,
        dest,
        count: od.matrix[origin]?.[dest] ?? 0,
        avgDurationS: od.avg_duration_s[`${origin}->${dest}`] ?? null,
        isDiagonal: origin === dest,
      });
    }
  }
  return cells;
}

/** Largest off-diagonal count, for scaling cell intensity. */
export function odPeak(od: ODMatrix): number {
  let peak = 0;
  for (const origin of od.zones) {
    for (const dest of od.zones) {
      if (origin === dest) continue;
      peak = Math.max(peak, od.matrix[origin]?.[dest] ?? 0);
    }
  }
  return peak;
}

export interface ODRollup {
  zone: string;
  outbound: number;
  inbound: number;
  net: number;
}

/** Per-zone inbound / outbound / net totals — a useful side panel. */
export function odRollups(od: ODMatrix): ODRollup[] {
  return od.zones.map((zone) => {
    const outbound = od.zones.reduce(
      (sum, dest) => sum + (od.matrix[zone]?.[dest] ?? 0),
      0,
    );
    const inbound = od.zones.reduce(
      (sum, origin) => sum + (od.matrix[origin]?.[zone] ?? 0),
      0,
    );
    return { zone, outbound, inbound, net: inbound - outbound };
  });
}

/** Total trips represented by the matrix. */
export function odTotal(od: ODMatrix): number {
  let total = 0;
  for (const origin of od.zones) {
    for (const dest of od.zones) total += od.matrix[origin]?.[dest] ?? 0;
  }
  return total;
}
