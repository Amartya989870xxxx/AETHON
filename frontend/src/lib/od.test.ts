import { describe, expect, it } from "vitest";
import type { ODMatrix } from "../api/types";
import { odCells, odPeak, odRollups, odTotal } from "./od";

const OD: ODMatrix = {
  zones: ["central", "east", "north"],
  matrix: {
    central: { central: 0, east: 36, north: 79 },
    east: { central: 43, east: 0, north: 10 },
    north: { central: 12, east: 5, north: 0 },
  },
  avg_duration_s: { "central->east": 812.4 },
  window: { start: "x", end: "y" },
};

describe("odCells", () => {
  it("emits one cell per zones × zones pair, row-major", () => {
    const cells = odCells(OD);
    expect(cells).toHaveLength(9);
    expect(cells[0]).toMatchObject({ origin: "central", dest: "central", isDiagonal: true, count: 0 });
    expect(cells[1]).toMatchObject({ origin: "central", dest: "east", count: 36, avgDurationS: 812.4 });
  });

  it("marks the diagonal", () => {
    const diag = odCells(OD).filter((c) => c.isDiagonal);
    expect(diag).toHaveLength(3);
    expect(diag.every((c) => c.count === 0)).toBe(true);
  });
});

describe("odPeak", () => {
  it("ignores the diagonal", () => {
    expect(odPeak(OD)).toBe(79);
  });
});

describe("odRollups", () => {
  it("computes inbound, outbound and net per zone", () => {
    const central = odRollups(OD).find((r) => r.zone === "central")!;
    expect(central.outbound).toBe(36 + 79);
    expect(central.inbound).toBe(43 + 12);
    expect(central.net).toBe(55 - 115);
  });
});

describe("odTotal", () => {
  it("sums every cell", () => {
    expect(odTotal(OD)).toBe(36 + 79 + 43 + 10 + 12 + 5);
  });
});
