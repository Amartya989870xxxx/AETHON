import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CircleMarker, Polyline, Popup, Tooltip } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngTuple } from "leaflet";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { MapView } from "../components/MapView";
import { StatTile } from "../components/StatTile";
import { Badge } from "../components/Badge";
import { Field, TextInput } from "../components/controls";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton, Spinner } from "../components/states";
import { Meter } from "../components/Meter";
import { SearchIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { searchPlates, getTrajectory } from "../api/endpoints";
import { useWindowParams } from "../components/TimeWindow";
import { pointToLatLng, toPolyline } from "../lib/geo";
import { matchStyle } from "../lib/enums";
import { classifyTrajectory, meanHopScore } from "../lib/trajectory";
import { distanceKm, num, pct } from "../lib/format";
import { formatDuration, formatLocal } from "../lib/datetime";
import type {
  Hop,
  PathNode,
  PlateMatch,
  RejectedHop,
  TrajectoryResponse,
} from "../api/types";

export function TrajectoryScreen() {
  const [params, setParams] = useSearchParams();
  const plate = params.get("plate");
  const setPlate = useCallback(
    (next: string | null) => {
      setParams(
        (p) => {
          if (next) p.set("plate", next);
          else p.delete("plate");
          return p;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const win = useWindowParams();

  useEffect(() => {
    const id = setTimeout(() => setDebounced(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const search = useApi(
    (signal) =>
      debounced.length >= 2
        ? searchPlates(debounced, win, signal)
        : Promise.resolve(null),
    [debounced, win.start, win.end],
  );

  const trajectory = useApi(
    (signal) =>
      plate ? getTrajectory(plate, win, signal) : Promise.resolve(null),
    [plate, win.start, win.end],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Vehicle trajectory"
        subtitle="Reconstruct one vehicle's route across the camera network"
      />

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        {/* --- search column --- */}
        <div className="space-y-4">
          <GlassPanel>
            <Field
              label="Plate search"
              hint="Partial is fine — a fragment of the registration or the numeric block."
            >
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-500">
                  <SearchIcon width={15} height={15} />
                </span>
                <TextInput
                  autoFocus
                  value={term}
                  onChange={(e) => setTerm(e.target.value.toUpperCase())}
                  placeholder="e.g. CAF or 3125"
                  className="pl-9"
                />
              </div>
            </Field>

            <div className="mt-4">
              {search.loading && debounced.length >= 2 && (
                <div className="flex items-center gap-2 py-2 text-xs text-ink-400">
                  <Spinner className="h-3 w-3" /> searching…
                </div>
              )}
              {search.error && (
                <ErrorState error={search.error} bare onRetry={search.refetch} />
              )}
              {search.data && (
                <SearchResults
                  matches={search.data.matches}
                  total={search.data.total_matches}
                  activePlate={plate}
                  onPick={setPlate}
                />
              )}
              {!search.data && !search.loading && debounced.length < 2 && (
                <p className="py-2 text-xs text-ink-500">
                  Type at least 2 characters to search sightings in the current
                  time window.
                </p>
              )}
            </div>
          </GlassPanel>
        </div>

        {/* --- result column --- */}
        <div className="space-y-6">
          {!plate ? (
            <GlassPanel>
              <EmptyState
                title="No vehicle selected"
                message="Search on the left and pick a plate to reconstruct its route. Trajectories already exist in the database — this screen queries and draws them, it doesn't trigger processing."
              />
            </GlassPanel>
          ) : trajectory.error ? (
            <ErrorState error={trajectory.error} onRetry={trajectory.refetch} />
          ) : trajectory.initial || !trajectory.data ? (
            <GlassPanel flush>
              <Skeleton className="h-[440px] w-full rounded-none" />
            </GlassPanel>
          ) : (
            <TrajectoryResult plate={plate} data={trajectory.data} />
          )}
        </div>
      </div>
    </div>
  );
}

function SearchResults({
  matches,
  total,
  activePlate,
  onPick,
}: {
  matches: PlateMatch[];
  total: number;
  activePlate: string | null;
  onPick: (plate: string) => void;
}) {
  if (matches.length === 0) {
    return (
      <p className="py-2 text-xs text-ink-500">
        No plates match that fragment in this window.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <p className="eyebrow">
        {matches.length} of {total} matches
      </p>
      <ul className="max-h-[420px] space-y-1.5 overflow-y-auto pr-1">
        {matches.map((m) => (
          <li key={m.plate}>
            <button
              onClick={() => onPick(m.plate)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition-all duration-300 ease-silk ${
                activePlate === m.plate
                  ? "border-accent-500/50 bg-accent-500/10"
                  : "border-white/[0.06] bg-white/[0.02] hover:border-accent-500/30 hover:bg-white/[0.04]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-medium text-ink-100">
                  {m.plate}
                </span>
                <span className="text-[11px] text-ink-400">
                  {m.sightings} sighting{m.sightings === 1 ? "" : "s"}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-ink-500">
                <span>{m.cameras.length} cameras · {m.vehicle_types.join(", ")}</span>
                <span>{pct(m.best_confidence)}</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TrajectoryResult({
  plate,
  data,
}: {
  plate: string;
  data: TrajectoryResponse;
}) {
  const view = classifyTrajectory(data);

  const nodeLatLngs = useMemo(
    () =>
      data.path
        .map(pointToLatLng)
        .filter((p): p is LatLngTuple => p !== null),
    [data.path],
  );
  const line = useMemo(() => toPolyline(data.path), [data.path]);
  const bounds: LatLngBoundsExpression | null =
    nodeLatLngs.length > 0 ? nodeLatLngs : null;

  const bridged = view.kind === "route" ? view.bridgedHopIndexes : [];

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="Route score"
          value={pct(data.score)}
          accent="#22d3ee"
          hint={data.fuzzy_used ? "fuzzy match used" : "exact plate match"}
        />
        <StatTile
          label="Distance"
          value={distanceKm(data.total_distance_km)}
          hint={`${data.path.length} sightings`}
        />
        <StatTile
          label="Duration"
          value={formatDuration(data.duration_seconds)}
          hint={`${data.candidates_considered} candidates`}
        />
        <StatTile
          label="Mean hop score"
          value={pct(meanHopScore(data))}
          empty={meanHopScore(data) == null}
          hint={`${data.hops.length} hops`}
        />
      </div>

      {view.kind !== "route" ? (
        <GlassPanel flush className="overflow-hidden">
          {nodeLatLngs.length === 1 ? (
            <div className="h-[380px]">
              <MapView bounds={bounds}>
                <CircleMarker
                  center={nodeLatLngs[0]}
                  radius={9}
                  pathOptions={{
                    color: "#22d3ee",
                    fillColor: "#22d3ee",
                    fillOpacity: 0.6,
                  }}
                >
                  <Tooltip permanent direction="top" offset={[0, -8]}>
                    <span className="text-xs">{data.path[0].camera_name}</span>
                  </Tooltip>
                </CircleMarker>
              </MapView>
            </div>
          ) : null}
          <EmptyState
            title={
              view.kind === "none" ? "No route to draw" : "Single sighting only"
            }
            message={view.message}
          />
        </GlassPanel>
      ) : (
        <GlassPanel flush className="overflow-hidden">
          <div className="h-[440px]">
            <MapView bounds={bounds}>
              <Polyline
                positions={line}
                pathOptions={{ color: "#22d3ee", weight: 3, opacity: 0.9 }}
              />
              {bridged.map((hopIdx) => {
                const hop = data.hops[hopIdx];
                const seg = [
                  pointToLatLng(data.path[hop.from_index]),
                  pointToLatLng(data.path[hop.to_index]),
                ].filter((p): p is LatLngTuple => p !== null);
                return (
                  <Polyline
                    key={`bridge-${hopIdx}`}
                    positions={seg}
                    pathOptions={{
                      color: "#ffcc4d",
                      weight: 3,
                      dashArray: "2 8",
                      opacity: 0.95,
                    }}
                  />
                );
              })}
              {data.path.map((node, i) => {
                const c = pointToLatLng(node);
                if (!c) return null;
                const isEnd = i === 0 || i === data.path.length - 1;
                return (
                  <CircleMarker
                    key={node.observation_id}
                    center={c}
                    radius={isEnd ? 8 : 5}
                    pathOptions={{
                      color: isEnd ? "#3b82f6" : "#22d3ee",
                      fillColor: isEnd ? "#3b82f6" : "#22d3ee",
                      fillOpacity: 0.7,
                      weight: 2,
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -6]}>
                      <span className="text-xs">
                        #{i + 1} · {node.camera_name} ·{" "}
                        {formatLocal(node.timestamp, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </Tooltip>
                    <Popup>
                      <PathNodePopup index={i} node={node} />
                    </Popup>
                  </CircleMarker>
                );
              })}
            </MapView>
          </div>
          {bridged.length > 0 && (
            <div className="border-t border-white/[0.06] px-4 py-2 text-[11px] text-ink-400">
              <span className="mr-1 inline-block h-2 w-4 rounded-full bg-[repeating-linear-gradient(90deg,#ffcc4d_0_3px,transparent_3px_9px)] align-middle" />
              dashed segments were bridged over cameras that never reported this
              plate
            </div>
          )}
        </GlassPanel>
      )}

      {data.hops.length > 0 && (
        <GlassPanel>
          <h3 className="eyebrow mb-3">Hops · {plate}</h3>
          <HopsTable hops={data.hops} path={data.path} />
        </GlassPanel>
      )}

      {data.rejected.length > 0 && <RejectedPanel rejected={data.rejected} />}
    </>
  );
}

function PathNodePopup({
  index,
  node,
}: {
  index: number;
  node: PathNode;
}) {
  return (
    <div className="min-w-[13rem] space-y-1.5 text-ink-100">
      <p className="text-sm font-semibold">
        #{index + 1} · {node.camera_name}
      </p>
      <p className="text-[11px] text-ink-400">
        {node.camera_id} · {node.road_segment} · zone {node.zone}
      </p>
      <p className="text-[11px]">{formatLocal(node.timestamp)}</p>
      <div className="flex flex-wrap gap-1 pt-1">
        <Badge size="sm" style={matchStyle(node.match)} />
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-ink-300">
          {node.vehicle_type}
        </span>
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-ink-300">
          {node.direction}
        </span>
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[11px] text-ink-300">
          conf {pct(node.confidence)}
        </span>
      </div>
    </div>
  );
}

function HopsTable({
  hops,
  path,
}: {
  hops: Hop[];
  path: PathNode[];
}) {
  const columns: Column<Hop>[] = [
    {
      key: "seg",
      header: "Segment",
      cell: (h) => (
        <span className="text-xs">
          {path[h.from_index]?.camera_id} → {path[h.to_index]?.camera_id}
          {h.intermediate_cameras.length > 0 && (
            <span className="ml-1 text-signal-medium">
              (+{h.intermediate_cameras.length})
            </span>
          )}
        </span>
      ),
    },
    {
      key: "time",
      header: "Time",
      align: "right",
      cell: (h) => formatDuration(h.seconds),
    },
    {
      key: "dist",
      header: "Dist",
      align: "right",
      cell: (h) => distanceKm(h.distance_km),
    },
    {
      key: "speed",
      header: "Implied",
      align: "right",
      cell: (h) => num(h.implied_speed_kmph, { unit: "km/h" }),
    },
    {
      key: "score",
      header: "Score",
      width: "w-40",
      cell: (h) => <Meter value={h.total} showValue color="#22d3ee" />,
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={hops}
      rowKey={(_, i) => i}
    />
  );
}

function RejectedPanel({
  rejected,
}: {
  rejected: RejectedHop[];
}) {
  const [open, setOpen] = useState(false);
  return (
    <GlassPanel>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between"
      >
        <span className="eyebrow">
          Why not these? · {rejected.length} rejected candidate
          {rejected.length === 1 ? "" : "s"}
        </span>
        <span className="text-xs text-ink-400">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <ul className="mt-3 space-y-2">
          {rejected.map((r, i) => (
            <li
              key={i}
              className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-ink-200">
                  {r.from_camera} → {r.to_camera}
                </span>
                <span className="text-signal-high">{r.reason}</span>
              </div>
              {Object.keys(r.detail).length > 0 && (
                <p className="mt-1 text-ink-500">
                  {Object.entries(r.detail)
                    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                    .join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </GlassPanel>
  );
}
