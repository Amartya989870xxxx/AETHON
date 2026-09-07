import { useEffect, type ReactNode } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";

interface Props {
  children?: ReactNode;
  /** Fit these bounds whenever they change (e.g. after data loads). */
  bounds?: LatLngBoundsExpression | null;
  center?: [number, number];
  zoom?: number;
  className?: string;
}

/**
 * Shared Leaflet map with the desaturated dark basemap. Every map screen
 * mounts this so the tile styling and attribution live in one place.
 *
 * Consumers that render GeoJSON should prefer react-leaflet's `<GeoJSON>` —
 * it reads `[lon, lat]` correctly without a manual swap.
 */
export function MapView({
  children,
  bounds,
  center = [12.97, 77.59], // Bengaluru-ish, matches the seeded demo city
  zoom = 12,
  className,
}: Props) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className={className ?? "h-full w-full"}
      zoomControl
      preferCanvas
      attributionControl
    >
      {/* Keyless OSM tiles, darkened to a night basemap by the CSS filter in
          index.css (.leaflet-tile). No API key, no tile-provider account. */}
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; OpenStreetMap contributors'
        maxZoom={19}
      />
      <FitBounds bounds={bounds} />
      {children}
    </MapContainer>
  );
}

function FitBounds({ bounds }: { bounds?: LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => {
    if (!bounds) return;
    try {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    } catch {
      /* empty / degenerate bounds — leave the map where it is */
    }
  }, [bounds, map]);
  return null;
}
