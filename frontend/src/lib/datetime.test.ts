import { describe, expect, it } from "vitest";
import {
  formatDuration,
  localInputToUtcParam,
  normalizeIso,
  parseUtc,
} from "./datetime";

describe("normalizeIso", () => {
  it("leaves an explicit +00:00 offset alone", () => {
    expect(normalizeIso("2026-09-07T14:38:16.503165+00:00")).toBe(
      "2026-09-07T14:38:16.503165+00:00",
    );
  });

  it("leaves a Z suffix alone", () => {
    expect(normalizeIso("2026-09-07T14:38:16Z")).toBe("2026-09-07T14:38:16Z");
  });

  it("appends Z to a suffix-less SQLite timestamp", () => {
    expect(normalizeIso("2026-09-07T12:20:31.965309")).toBe(
      "2026-09-07T12:20:31.965309Z",
    );
  });

  it("handles a negative offset", () => {
    expect(normalizeIso("2026-09-07T12:20:31-05:30")).toBe(
      "2026-09-07T12:20:31-05:30",
    );
  });
});

describe("parseUtc", () => {
  it("treats a suffix-less timestamp as UTC, not local", () => {
    const withZ = parseUtc("2026-09-07T12:00:00Z");
    const without = parseUtc("2026-09-07T12:00:00");
    expect(without.getTime()).toBe(withZ.getTime());
  });

  it("parses the two documented forms to the same instant", () => {
    const a = parseUtc("2026-09-07T12:20:31.965309+00:00");
    const b = parseUtc("2026-09-07T12:20:31.965309");
    expect(a.getTime()).toBe(b.getTime());
  });
});

describe("localInputToUtcParam", () => {
  it("returns undefined for an empty value so the 24h default applies", () => {
    expect(localInputToUtcParam("")).toBeUndefined();
  });

  it("produces a Z-suffixed ISO string", () => {
    const out = localInputToUtcParam("2026-09-07T12:00");
    expect(out).toMatch(/Z$/);
  });
});

describe("formatDuration", () => {
  it("renders sub-minute", () => expect(formatDuration(42)).toBe("42s"));
  it("renders minutes and seconds", () =>
    expect(formatDuration(1072)).toBe("17m 52s"));
  it("renders hours and minutes", () =>
    expect(formatDuration(3860)).toBe("1h 04m"));
  it("handles null", () => expect(formatDuration(null)).toBe("—"));
});
