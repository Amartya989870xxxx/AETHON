/**
 * GeoJSON `coordinates` are `[longitude, latitude]`. Leaflet's `LatLng`
 * constructor and `L.marker` want `[latitude, longitude]` — the reverse.
 *
 * Where we hand `<GeoJSON>` a whole FeatureCollection, react-leaflet does the
 * swap for us and we don't touch coordinates at all. These helpers are only
 * for the places we build geometry by hand — chiefly the trajectory polyline,
 * whose points come from `path[].lat` / `path[].lon` (already split, but we
 * still want one funnel for the ordering rule).
 */
import type { LatLngExpression, LatLngTuple } from "leaflet";

/** GeoJSON `[lon, lat]` -> Leaflet `[lat, lon]`. */
export function lonLatToLatLng(coord: [number, number]): LatLngTuple {
  const [lon, lat] = coord;
  return [lat, lon];
}

/** A `{ lat, lon }` pair (trajectory path node shape) -> Leaflet `[lat, lon]`. */
export function pointToLatLng(p: {
  lat: number | null;
  lon: number | null;
}): LatLngTuple | null {
  if (p.lat == null || p.lon == null) return null;
  return [p.lat, p.lon];
}

/** Build a Leaflet polyline path from ordered path nodes, dropping any that
 *  lack coordinates. The input order is preserved — it is already the
 *  reconstructed route, not raw sightings. */
export function toPolyline(
  nodes: { lat: number | null; lon: number | null }[],
): LatLngExpression[] {
  return nodes
    .map(pointToLatLng)
    .filter((p): p is LatLngTuple => p !== null);
}

/** Rough centroid of a set of `[lat, lon]` points, for map centering. */
export function centroid(points: LatLngTuple[]): LatLngTuple | null {
  if (points.length === 0) return null;
  const sum = points.reduce(
    (acc, [lat, lon]) => [acc[0] + lat, acc[1] + lon] as LatLngTuple,
    [0, 0] as LatLngTuple,
  );
  return [sum[0] / points.length, sum[1] / points.length];
}
