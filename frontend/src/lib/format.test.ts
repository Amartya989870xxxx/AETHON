import { describe, expect, it } from "vitest";
import { count, distanceKm, humanize, nullable, num, pct } from "./format";

describe("pct", () => {
  it("multiplies a 0..1 confidence by 100", () => {
    expect(pct(0.94)).toBe("94%");
  });
  it("supports decimals", () => expect(pct(0.2698, 1)).toBe("27.0%"));
  it("renders a dash for null", () => expect(pct(null)).toBe("—"));
});

describe("nullable", () => {
  it("renders the value when present", () => {
    expect(nullable(23.3, (v) => `${v} km/h`)).toBe("23.3 km/h");
  });
  it("renders the fallback for null", () => {
    expect(nullable(null, (v) => `${v}`)).toBe("not enough history yet");
  });
  it("renders zero, not the fallback", () => {
    expect(nullable(0, (v) => `${v}`)).toBe("0");
  });
});

describe("num", () => {
  it("honours the null fallback", () => {
    expect(num(null, { fallback: "no data" })).toBe("no data");
  });
  it("formats with unit", () => expect(num(58.9, { unit: "km/h" })).toBe("58.9 km/h"));
});

describe("count", () => {
  it("adds separators", () => expect(count(12000)).toBe("12,000"));
});

describe("humanize", () => {
  it("title-cases snake_case", () =>
    expect(humanize("impossible_travel")).toBe("Impossible Travel"));
});

describe("distanceKm", () => {
  it("uses metres below 1km", () => expect(distanceKm(0.82)).toBe("820 m"));
  it("uses km above", () => expect(distanceKm(9.63)).toBe("9.63 km"));
});
