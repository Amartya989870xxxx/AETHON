/**
 * Classifies a trajectory response into the state the UI should render.
 * The backend has several valid "not a route" outcomes that look similar but
 * need different copy:
 *
 *  - found === false                -> no sightings at all in the window
 *  - found === true, path.length 1  -> a single sighting, nothing to draw
 *  - found === true, path.length >1 -> a real route (may still have bridged gaps)
 */
import type { TrajectoryResponse } from "../api/types";

export type TrajectoryView =
  | { kind: "none"; message: string }
  | { kind: "single"; message: string }
  | { kind: "route"; bridgedHopIndexes: number[] };

export function classifyTrajectory(r: TrajectoryResponse): TrajectoryView {
  if (!r.found || r.path.length === 0) {
    return {
      kind: "none",
      message:
        r.note || "No sightings of this plate in the selected time window.",
    };
  }

  if (r.path.length === 1) {
    return {
      kind: "single",
      message:
        r.note || "Single sighting — no route to reconstruct yet.",
    };
  }

  const bridgedHopIndexes = r.hops
    .map((hop, i) => (hop.intermediate_cameras.length > 0 ? i : -1))
    .filter((i) => i >= 0);

  return { kind: "route", bridgedHopIndexes };
}

/** True if any hop bridged over a camera that never reported this plate. */
export function hasBridgedGaps(r: TrajectoryResponse): boolean {
  return r.hops.some((h) => h.intermediate_cameras.length > 0);
}

/** Mean hop confidence (`hop.total`), for a headline quality read. */
export function meanHopScore(r: TrajectoryResponse): number | null {
  if (r.hops.length === 0) return null;
  return r.hops.reduce((s, h) => s + h.total, 0) / r.hops.length;
}
