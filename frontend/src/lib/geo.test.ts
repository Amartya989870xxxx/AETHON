import { describe, expect, it } from "vitest";
import { centroid, lonLatToLatLng, toPolyline } from "./geo";

describe("lonLatToLatLng", () => {
  it("swaps GeoJSON [lon, lat] to Leaflet [lat, lon]", () => {
    // API feature: coordinates [77.59, 12.995] == lon 77.59, lat 12.995
    expect(lonLatToLatLng([77.59, 12.995])).toEqual([12.995, 77.59]);
  });
});

describe("toPolyline", () => {
  it("keeps the given order and drops coordinate-less nodes", () => {
    const nodes = [
      { lat: 13.005, lon: 77.585 },
      { lat: null, lon: null },
      { lat: 12.995, lon: 77.59 },
    ];
    expect(toPolyline(nodes)).toEqual([
      [13.005, 77.585],
      [12.995, 77.59],
    ]);
  });

  it("returns empty for a single coordinate-less node", () => {
    expect(toPolyline([{ lat: null, lon: null }])).toEqual([]);
  });
});

describe("centroid", () => {
  it("returns null for no points", () => expect(centroid([])).toBeNull());
  it("averages lat and lon", () => {
    expect(centroid([[0, 0], [10, 20]])).toEqual([5, 10]);
  });
});
