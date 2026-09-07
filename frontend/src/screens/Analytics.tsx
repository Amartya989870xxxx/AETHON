import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { StatTile } from "../components/StatTile";
import { Button, Select } from "../components/controls";
import { DataTable, type Column } from "../components/DataTable";
import { Meter } from "../components/Meter";
import { TimeWindowPicker, useWindowParams } from "../components/TimeWindow";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/states";
import { RefreshIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useToast } from "../components/toast";
import {
  getAnalyticsSummary,
  getBottlenecks,
  getOD,
  getSegmentSeries,
  recomputeAnalytics,
} from "../api/endpoints";
import { odCells, odPeak, odRollups, odTotal } from "../lib/od";
import { congestionColor } from "../lib/enums";
import { count, num } from "../lib/format";
import { formatLocal } from "../lib/datetime";
import type { BottleneckRow, ODMatrix } from "../api/types";

export function AnalyticsScreen() {
  const win = useWindowParams();
  const toast = useToast();
  const [busyRecompute, setBusyRecompute] = useState(false);

  const summary = useApi((signal) => getAnalyticsSummary(signal), []);
  const bottlenecks = useApi(
    (signal) => getBottlenecks(win, signal),
    [win.start, win.end],
  );
  const od = useApi((signal) => getOD(win, signal), [win.start, win.end]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        subtitle="City-wide flow: bottlenecks, origin-destination, and segment trends"
        actions={
          <>
            <TimeWindowPicker />
            <Button
              size="sm"
              loading={busyRecompute}
              onClick={async () => {
                setBusyRecompute(true);
                try {
                  const r = await recomputeAnalytics(win);
                  toast.push({
                    kind: "success",
                    title: "Analytics recomputed",
                    body: `${r.buckets_written} buckets · ${r.od_cells_written} OD cells written.`,
                  });
                  summary.refetch();
                  bottlenecks.refetch();
                  od.refetch();
                } catch (err) {
                  toast.push({
                    kind: "error",
                    title: "Recompute failed",
                    body: (err as Error).message,
                  });
                } finally {
                  setBusyRecompute(false);
                }
              }}
            >
              Recompute
            </Button>
            <Button
              size="sm"
              icon={<RefreshIcon />}
              onClick={() => {
                summary.refetch();
                bottlenecks.refetch();
                od.refetch();
              }}
            >
              Refresh
            </Button>
          </>
        }
      />

      {/* summary tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile
          label="Cameras reporting"
          value={summary.initial ? "…" : (summary.data?.cameras_reporting ?? 0)}
          hint={`live ${summary.data?.live_window_minutes ?? 30} min window`}
        />
        <StatTile
          label="Vehicles (live)"
          value={
            summary.initial ? "…" : count(summary.data?.vehicles_in_window ?? 0)
          }
        />
        <StatTile
          label="Congested cameras"
          value={
            summary.initial
              ? "…"
              : (summary.data?.congested_cameras.length ?? 0)
          }
          accent={
            summary.data?.congested_cameras.length ? "#ff8f4c" : undefined
          }
        />
        <StatTile
          label="Mean speed (live)"
          value={num(summary.data?.mean_speed_kmph, { unit: "km/h" })}
          empty={!summary.data || summary.data.mean_speed_kmph == null}
        />
      </div>

      {summary.error && (
        <ErrorState error={summary.error} onRetry={summary.refetch} />
      )}

      {/* segment trend — full width, it's the "when does this road congest" view */}
      <SegmentTrend
        segments={(bottlenecks.data?.bottlenecks ?? []).map(
          (b) => b.road_segment,
        )}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* bottlenecks */}
        <GlassPanel>
          <h3 className="eyebrow mb-3">Bottlenecks · ranked</h3>
          {bottlenecks.error ? (
            <ErrorState error={bottlenecks.error} bare onRetry={bottlenecks.refetch} />
          ) : bottlenecks.initial ? (
            <SkeletonRows rows={8} />
          ) : (
            <BottlenecksTable rows={bottlenecks.data?.bottlenecks ?? []} />
          )}
        </GlassPanel>

        {/* OD matrix */}
        <GlassPanel>
          <h3 className="eyebrow mb-3">Origin → destination · zone flow</h3>
          {od.error ? (
            <ErrorState error={od.error} bare onRetry={od.refetch} />
          ) : od.initial ? (
            <Skeleton className="h-64 w-full" />
          ) : !od.data || od.data.zones.length === 0 ? (
            <EmptyState
              title="No OD data for this window"
              message="Origin-destination flow is aggregated from completed cross-zone trips. Widen the time window or run Recompute."
            />
          ) : (
            <ODMatrixView data={od.data} />
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function BottlenecksTable({ rows }: { rows: BottleneckRow[] }) {
  const columns: Column<BottleneckRow>[] = [
    {
      key: "segment",
      header: "Segment",
      cell: (r) => <span className="text-ink-100">{r.road_segment}</span>,
    },
    {
      key: "share",
      header: "Congested",
      width: "w-32",
      cell: (r) => (
        <Meter
          value={r.congested_share}
          showValue
          color={congestionColor(r.avg_congestion_score)}
        />
      ),
    },
    {
      key: "speed",
      header: "Avg speed",
      align: "right",
      cell: (r) => num(r.avg_speed_kmph, { unit: "km/h", fallback: "—" }),
    },
    {
      key: "vol",
      header: "Vehicles",
      align: "right",
      cell: (r) => count(r.total_vehicles),
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.road_segment}
      minWidth={440}
      empty={
        <p className="py-8 text-center text-xs text-ink-500">
          No segment aggregates in this window.
        </p>
      }
    />
  );
}

function SegmentTrend({ segments }: { segments: string[] }) {
  const win = useWindowParams();
  const [segment, setSegment] = useState<string>("");

  useEffect(() => {
    if (!segment && segments.length > 0) setSegment(segments[0]);
  }, [segments, segment]);

  const series = useApi(
    (signal) =>
      segment
        ? getSegmentSeries(segment, win, signal)
        : Promise.resolve(null),
    [segment, win.start, win.end],
  );

  const data = useMemo(
    () =>
      (series.data?.series ?? []).map((p) => ({
        t: formatLocal(p.bucket_start, {
          month: "short",
          day: "2-digit",
          hour: "2-digit",
        }),
        congestion: Number((p.congestion_score * 100).toFixed(1)),
        vehicles: p.vehicle_count,
        speed: p.avg_speed_kmph,
      })),
    [series.data],
  );

  return (
    <GlassPanel>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h3 className="eyebrow">Segment trend</h3>
        <div className="flex items-center gap-3">
          <Legend swatch="#8b5cf6" label="Congestion %" />
          <Legend swatch="#5cd0c0" label="Speed km/h" />
          <Select
            value={segment}
            onChange={(e) => setSegment(e.target.value)}
            className="w-auto max-w-[14rem]"
          >
            {segments.length === 0 && <option value="">no segments</option>}
            {segments.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {series.error ? (
        <ErrorState error={series.error} bare onRetry={series.refetch} />
      ) : !segment ? (
        <EmptyState
          title="Pick a segment"
          message="Choose a road above to see its congestion over time."
        />
      ) : series.initial ? (
        <Skeleton className="h-64 w-full" />
      ) : data.length === 0 ? (
        <EmptyState
          title="No buckets in window"
          message={`No aggregates for ${segment} in the selected time range.`}
        />
      ) : (
        <div className="mt-2 h-64 w-full">
          <ResponsiveContainer>
            <AreaChart
              data={data}
              margin={{ top: 8, right: 12, bottom: 0, left: 4 }}
            >
              <defs>
                <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="t"
                tick={{ fill: "#5b6070", fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                minTickGap={40}
              />
              <YAxis
                yAxisId="pct"
                tick={{ fill: "#8b5cf6", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={34}
                domain={[0, (max: number) => Math.ceil((max + 5) / 10) * 10]}
                tickFormatter={(v: number) => `${v}`}
              />
              <YAxis
                yAxisId="spd"
                orientation="right"
                tick={{ fill: "#5cd0c0", fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={34}
              />
              <RTooltip
                contentStyle={{
                  background: "rgba(16,17,22,0.96)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 12,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#c4c8d4" }}
              />
              <Area
                yAxisId="pct"
                type="monotone"
                dataKey="congestion"
                name="Congestion"
                stroke="#8b5cf6"
                strokeWidth={2}
                fill="url(#cg)"
                unit="%"
                isAnimationActive={false}
              />
              <Line
                yAxisId="spd"
                type="monotone"
                dataKey="speed"
                name="Speed"
                stroke="#5cd0c0"
                strokeWidth={1.5}
                dot={false}
                unit=" km/h"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </GlassPanel>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-ink-400">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: swatch }}
      />
      {label}
    </span>
  );
}

function ODMatrixView({ data }: { data: ODMatrix }) {
  const peak = odPeak(data) || 1;
  const cells = odCells(data);
  const rollups = odRollups(data);
  const total = odTotal(data);

  return (
    <div className="space-y-4">
      <p className="text-xs text-ink-500">
        {count(total)} cross-zone trips · diagonal is always 0 (intra-zone trips
        excluded)
      </p>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="p-1 text-left font-medium text-ink-500">
                from ↓ / to →
              </th>
              {data.zones.map((z) => (
                <th key={z} className="p-1 font-medium capitalize text-ink-400">
                  {z}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.zones.map((origin) => (
              <tr key={origin}>
                <td className="p-1 font-medium capitalize text-ink-400">
                  {origin}
                </td>
                {data.zones.map((dest) => {
                  const cell = cells.find(
                    (c) => c.origin === origin && c.dest === dest,
                  )!;
                  const intensity = cell.isDiagonal ? 0 : cell.count / peak;
                  return (
                    <td
                      key={dest}
                      title={
                        cell.avgDurationS
                          ? `${cell.count} trips · avg ${Math.round(
                              cell.avgDurationS / 60,
                            )} min`
                          : `${cell.count} trips`
                      }
                      className="h-10 w-14 rounded text-center tabular-nums"
                      style={{
                        background: cell.isDiagonal
                          ? "rgba(255,255,255,0.02)"
                          : `rgba(139,92,246,${0.08 + intensity * 0.5})`,
                        color: intensity > 0.5 ? "#fff" : "#c4c8d4",
                      }}
                    >
                      {cell.isDiagonal ? "—" : cell.count}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rollups.map((r) => (
          <div
            key={r.zone}
            className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2"
          >
            <p className="text-xs font-medium capitalize text-ink-200">
              {r.zone}
            </p>
            <p className="mt-1 text-[11px] text-ink-500">
              in {r.inbound} · out {r.outbound} ·{" "}
              <span
                className={
                  r.net > 0
                    ? "text-signal-ok"
                    : r.net < 0
                      ? "text-signal-high"
                      : "text-ink-500"
                }
              >
                net {r.net > 0 ? "+" : ""}
                {r.net}
              </span>
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
