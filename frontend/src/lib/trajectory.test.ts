import { describe, expect, it } from "vitest";
import type { TrajectoryResponse } from "../api/types";
import { classifyTrajectory, hasBridgedGaps, meanHopScore } from "./trajectory";

function base(overrides: Partial<TrajectoryResponse>): TrajectoryResponse {
  return {
    plate: "RJ25CD3929",
    found: true,
    score: 0.5,
    path: [],
    hops: [],
    rejected: [],
    total_distance_km: 0,
    duration_seconds: 0,
    candidates_considered: 0,
    fuzzy_used: false,
    note: "",
    ...overrides,
  };
}

const node = { camera_id: "C1" } as unknown as TrajectoryResponse["path"][number];
const hop = (intermediate: string[]) =>
  ({ intermediate_cameras: intermediate, total: 0.9 }) as unknown as TrajectoryResponse["hops"][number];

describe("classifyTrajectory", () => {
  it("found:false -> none", () => {
    const v = classifyTrajectory(base({ found: false }));
    expect(v.kind).toBe("none");
  });

  it("found:true with empty path -> none", () => {
    expect(classifyTrajectory(base({ found: true, path: [] })).kind).toBe("none");
  });

  it("single sighting -> single", () => {
    const v = classifyTrajectory(base({ path: [node] }));
    expect(v.kind).toBe("single");
  });

  it("multi-node path -> route, with bridged hop indexes", () => {
    const v = classifyTrajectory(
      base({
        path: [node, node, node],
        hops: [hop([]), hop(["C7"])],
      }),
    );
    expect(v).toEqual({ kind: "route", bridgedHopIndexes: [1] });
  });
});

describe("hasBridgedGaps", () => {
  it("true when a hop has intermediate cameras", () => {
    expect(hasBridgedGaps(base({ hops: [hop([]), hop(["C9"])] }))).toBe(true);
  });
  it("false otherwise", () => {
    expect(hasBridgedGaps(base({ hops: [hop([])] }))).toBe(false);
  });
});

describe("meanHopScore", () => {
  it("null for no hops", () => expect(meanHopScore(base({}))).toBeNull());
  it("averages hop.total", () =>
    expect(meanHopScore(base({ hops: [hop([]), hop([])] }))).toBeCloseTo(0.9));
});
