import { useMemo, useState } from "react";
import { CircleMarker, Popup, Tooltip } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngTuple } from "leaflet";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { MapView } from "../components/MapView";
import { StatTile } from "../components/StatTile";
import { Badge } from "../components/Badge";
import { Button, SegmentedControl } from "../components/controls";
import { ErrorState, Skeleton } from "../components/states";
import { RefreshIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useInterval } from "../hooks/useInterval";
import { getCameras, getHeatmap } from "../api/endpoints";
import { lonLatToLatLng } from "../lib/geo";
import { congestionColor } from "../lib/enums";
import { num, pct, count } from "../lib/format";
import { formatLocalTime } from "../lib/datetime";
import type { HeatmapProps } from "../api/types";

const WINDOWS = [
  { value: "30", label: "30 min" },
  { value: "60", label: "1 hr" },
  { value: "90", label: "90 min" },
  { value: "120", label: "2 hr" },
];

const POLL_MS = 20_000;

export function CityMapScreen() {
  const [windowMin, setWindowMin] = useState("60");
  const [colorMode, setColorMode] = useState<"boolean" | "score">("boolean");

  const cameras = useApi((signal) => getCameras(signal), []);
  const heatmap = useApi(
    (signal) => getHeatmap(Number(windowMin), signal),
    [windowMin],
  );

  useInterval(() => heatmap.refetch(), POLL_MS);

  const congestionByCamera = useMemo(() => {
    const map = new Map<string, HeatmapProps>();
    for (const f of heatmap.data?.features ?? []) {
      map.set(f.properties.camera_id, f.properties);
    }
    return map;
  }, [heatmap.data]);

  const points: LatLngTuple[] = useMemo(
    () =>
      (cameras.data?.features ?? []).map((f) =>
        lonLatToLatLng(f.geometry.coordinates),
      ),
    [cameras.data],
  );

  const bounds: LatLngBoundsExpression | null =
    points.length > 0 ? points : null;

  const stats = useMemo(() => {
    const feats = heatmap.data?.features ?? [];
    const congested = feats.filter((f) => f.properties.is_congested).length;
    const vehicles = feats.reduce(
      (s, f) => s + f.properties.vehicle_count,
      0,
    );
    const speeds = feats
      .map((f) => f.properties.avg_speed_kmph)
      .filter((v): v is number => v != null);
    return {
      total: cameras.data?.features.length ?? 0,
      reporting: feats.length,
      congested,
      vehicles,
      meanSpeed: speeds.length
        ? speeds.reduce((a, b) => a + b, 0) / speeds.length
        : null,
    };
  }, [cameras.data, heatmap.data]);

  if (cameras.error) {
    return (
      <div className="space-y-6">
        <PageHeader title="City map" />
        <ErrorState error={cameras.error} onRetry={cameras.refetch} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="City map"
        subtitle="Camera network and live congestion overlay"
        actions={
          <>
            <SegmentedControl
              options={WINDOWS}
              value={windowMin}
              onChange={setWindowMin}
            />
            <Button
              size="sm"
              icon={<RefreshIcon />}
              onClick={() => heatmap.refetch()}
              loading={heatmap.loading && !heatmap.initial}
            >
              Refresh
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="Cameras online"
          value={`${stats.total}`}
          hint={`${stats.reporting} reporting in window`}
        />
        <StatTile
          label="Congested now"
          value={`${stats.congested}`}
          accent={stats.congested ? "#ff8f4c" : undefined}
          hint="above segment baseline"
        />
        <StatTile
          label="Vehicles in window"
          value={count(stats.vehicles)}
          hint={`last ${windowMin} min`}
        />
        <StatTile
          label="Mean speed"
          value={num(stats.meanSpeed, { unit: "km/h" })}
          empty={stats.meanSpeed == null}
          hint="across reporting cameras"
        />
      </div>

      <GlassPanel flush className="overflow-hidden">
        <div className="relative h-[560px] w-full">
          {cameras.initial ? (
            <Skeleton className="h-full w-full rounded-none" />
          ) : (
            <MapView bounds={bounds}>
              {(cameras.data?.features ?? []).map((f) => {
                const id = f.properties.camera_id;
                const c = congestionByCamera.get(id);
                const center = lonLatToLatLng(f.geometry.coordinates);
                const color = !c
                  ? "#5b6070"
                  : colorMode === "score"
                    ? congestionColor(c.congestion_score)
                    : c.is_congested
                      ? "#fb5b6b"
                      : "#4ade80";
                return (
                  <CircleMarker
                    key={id}
                    center={center}
                    radius={c?.is_congested ? 9 : 6}
                    pathOptions={{
                      color,
                      fillColor: color,
                      fillOpacity: c ? 0.55 : 0.25,
                      weight: c?.is_congested ? 2 : 1,
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -6]} opacity={1}>
                      <span className="text-xs font-medium">
                        {f.properties.name}
                      </span>
                    </Tooltip>
                    <Popup>
                      <CameraPopup
                        name={f.properties.name}
                        id={id}
                        segment={f.properties.road_segment}
                        zone={f.properties.zone}
                        lanes={f.properties.lanes}
                        restricted={f.properties.is_restricted}
                        congestion={c ?? null}
                      />
                    </Popup>
                  </CircleMarker>
                );
              })}
            </MapView>
          )}

          <MapLegend
            colorMode={colorMode}
            onColorMode={setColorMode}
            stale={heatmap.error != null}
            updated={heatmap.data?.window?.end}
          />
        </div>
      </GlassPanel>
    </div>
  );
}

function CameraPopup({
  name,
  id,
  segment,
  zone,
  lanes,
  restricted,
  congestion,
}: {
  name: string;
  id: string;
  segment: string;
  zone: string;
  lanes: number;
  restricted: boolean;
  congestion: HeatmapProps | null;
}) {
  return (
    <div className="min-w-[13rem] space-y-2 text-ink-100">
      <div>
        <p className="text-sm font-semibold">{name}</p>
        <p className="text-[11px] text-ink-400">
          {id} · {segment} · zone {zone} · {lanes} lanes
        </p>
      </div>
      {restricted && (
        <Badge
          size="sm"
          style={{
            label: "Restricted zone",
            color: "#ff8f4c",
            bg: "#ff8f4c1f",
            border: "#ff8f4c59",
          }}
        />
      )}
      {congestion ? (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <dt className="text-ink-400">Congestion</dt>
          <dd className="tabular-nums">
            {pct(congestion.congestion_score, 1)}
            {congestion.is_congested && (
              <span className="ml-1 text-signal-critical">· congested</span>
            )}
          </dd>
          <dt className="text-ink-400">Vehicles</dt>
          <dd className="tabular-nums">{congestion.vehicle_count}</dd>
          <dt className="text-ink-400">Avg speed</dt>
          <dd className="tabular-nums">
            {num(congestion.avg_speed_kmph, { unit: "km/h", fallback: "—" })}
          </dd>
          <dt className="text-ink-400">z-score</dt>
          <dd className="tabular-nums">
            {num(congestion.z_score, { digits: 2, fallback: "—" })}
          </dd>
        </dl>
      ) : (
        <p className="text-[11px] text-ink-500">
          No observations in this window — no congestion data.
        </p>
      )}
    </div>
  );
}

function MapLegend({
  colorMode,
  onColorMode,
  stale,
  updated,
}: {
  colorMode: "boolean" | "score";
  onColorMode: (m: "boolean" | "score") => void;
  stale: boolean;
  updated?: string;
}) {
  return (
    <div className="glass absolute bottom-3 left-3 z-[500] w-56 p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="eyebrow">Congestion</span>
        <button
          onClick={() =>
            onColorMode(colorMode === "boolean" ? "score" : "boolean")
          }
          className="text-[10px] text-violet-400 hover:text-violet-300"
        >
          {colorMode === "boolean" ? "gradient" : "on / off"}
        </button>
      </div>
      {colorMode === "boolean" ? (
        <div className="space-y-1.5">
          <LegendRow color="#4ade80" label="Free flowing" />
          <LegendRow color="#fb5b6b" label="Congested (above baseline)" />
          <LegendRow color="#5b6070" label="No data this window" />
        </div>
      ) : (
        <>
          <div className="h-2 rounded-full bg-gradient-to-r from-[#3aa0ff] via-[#ffcc4d] to-[#fb5b6b]" />
          <div className="mt-1 flex justify-between text-[10px] text-ink-500">
            <span>calm</span>
            <span>severe</span>
          </div>
        </>
      )}
      <p className="mt-2 text-[10px] text-ink-500">
        {stale
          ? "overlay unavailable — showing cameras only"
          : updated
            ? `updated ${formatLocalTime(updated)} · auto every 20s`
            : "auto-refresh every 20s"}
      </p>
    </div>
  );
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="text-ink-300">{label}</span>
    </div>
  );
}
