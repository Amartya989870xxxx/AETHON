/**
 * Typed wrappers for every AETHON endpoint the dashboard uses.
 *
 * Transcribed from `backend/app/api/*` and `backend/app/engines/*`. Time
 * windows: omit `start`/`end` and the backend defaults to the last 24h
 * (`deps.py::time_window`) — callers only pass them when the user picks a range.
 */
import { apiFetch } from "./client";
import { OPERATOR_NAME } from "./config";
import type {
  AcknowledgeBody,
  Alert,
  AlertStats,
  AnalyticsSummary,
  AuditResponse,
  BlacklistBody,
  BlacklistEntry,
  BottlenecksResponse,
  CameraCollection,
  DemoStatus,
  HeatmapCollection,
  IngestResult,
  Observation,
  ObservationBody,
  ODMatrix,
  PlateSearchResponse,
  SegmentSeriesResponse,
  TrajectoryResponse,
} from "./types";

export type Window = {
  start?: string;
  end?: string;
};

// --- System / map --------------------------------------------------------

export const getCameras = (signal?: AbortSignal) =>
  apiFetch<CameraCollection>("/api/cameras", { signal });

export const getHeatmap = (windowMinutes = 30, signal?: AbortSignal) =>
  apiFetch<HeatmapCollection>("/api/analytics/heatmap", {
    query: { window_minutes: windowMinutes },
    signal,
  });

// --- Trajectory --------------------------------------------------------

export const searchPlates = (
  partial: string,
  opts: Window & { vehicle_type?: string } = {},
  signal?: AbortSignal,
) =>
  apiFetch<PlateSearchResponse>("/api/plates/search", {
    query: { partial, ...opts },
    signal,
  });

export const getTrajectory = (
  plate: string,
  opts: Window & { actor?: string } = {},
  signal?: AbortSignal,
) =>
  apiFetch<TrajectoryResponse>(`/api/trajectory/${encodeURIComponent(plate)}`, {
    query: { actor: opts.actor ?? OPERATOR_NAME, start: opts.start, end: opts.end },
    signal,
  });

// --- Alerts ----------------------------------------------------------

export const getAlerts = (
  opts: {
    status?: string;
    alert_type?: string;
    severity?: string;
    limit?: number;
  } = {},
  signal?: AbortSignal,
) => apiFetch<Alert[]>("/api/alerts", { query: { limit: 100, ...opts }, signal });

export const getAlert = (id: number, signal?: AbortSignal) =>
  apiFetch<Alert>(`/api/alerts/${id}`, { signal });

export const getAlertStats = (signal?: AbortSignal) =>
  apiFetch<AlertStats>("/api/alerts/stats/summary", { signal });

export const acknowledgeAlert = (id: number, body: AcknowledgeBody) =>
  apiFetch<Alert>(`/api/alerts/${id}/acknowledge`, { method: "POST", body });

// --- Analytics ------------------------------------------------------

export const getAnalyticsSummary = (signal?: AbortSignal) =>
  apiFetch<AnalyticsSummary>("/api/analytics/summary", { signal });

export const getBottlenecks = (
  opts: Window & { limit?: number } = {},
  signal?: AbortSignal,
) =>
  apiFetch<BottlenecksResponse>("/api/analytics/bottlenecks", {
    query: { limit: 15, ...opts },
    signal,
  });

export const getOD = (opts: Window = {}, signal?: AbortSignal) =>
  apiFetch<ODMatrix>("/api/analytics/od", { query: opts, signal });

export const getSegmentSeries = (
  segment: string,
  opts: Window = {},
  signal?: AbortSignal,
) =>
  apiFetch<SegmentSeriesResponse>(
    `/api/analytics/segment/${encodeURIComponent(segment)}`,
    { query: opts, signal },
  );

export const recomputeAnalytics = (opts: Window = {}) =>
  apiFetch<{ buckets_written: number; od_cells_written: number }>(
    "/api/analytics/recompute",
    { method: "POST", query: opts },
  );

// --- Watch list ----------------------------------------------------

export const getBlacklist = (activeOnly = true, signal?: AbortSignal) =>
  apiFetch<BlacklistEntry[]>("/api/blacklist", {
    query: { active_only: activeOnly },
    signal,
  });

export const addBlacklist = (body: BlacklistBody) =>
  apiFetch<BlacklistEntry>("/api/blacklist", { method: "POST", body });

export const removeBlacklist = (plate: string, actor = OPERATOR_NAME) =>
  apiFetch<{ plate_norm: string; active: boolean }>(
    `/api/blacklist/${encodeURIComponent(plate)}`,
    { method: "DELETE", query: { actor } },
  );

// --- Audit --------------------------------------------------------

export const getAudit = (
  opts: Window & {
    actor?: string;
    action?: string;
    subject?: string;
    limit?: number;
  } = {},
  signal?: AbortSignal,
) => apiFetch<AuditResponse>("/api/audit", { query: { limit: 200, ...opts }, signal });

// --- Observations ------------------------------------------------

export const getObservations = (
  opts: Window & {
    plate?: string;
    camera_id?: string;
    min_confidence?: number;
    limit?: number;
  } = {},
  signal?: AbortSignal,
) =>
  apiFetch<Observation[]>("/api/observations", {
    query: { limit: 200, ...opts },
    signal,
  });

export const postObservation = (body: ObservationBody) =>
  apiFetch<IngestResult>("/api/observations", { method: "POST", body });

// --- Demo driver (dev-only presentation tool) -------------------

export const startDemo = (durationS = 120, speed = 60) =>
  apiFetch<{ status: string }>("/api/demo/start", {
    method: "POST",
    query: { duration_s: durationS, speed },
  });

export const stopDemo = () =>
  apiFetch<{ status: string }>("/api/demo/stop", { method: "POST" });

export const getDemoStatus = (signal?: AbortSignal) =>
  apiFetch<DemoStatus>("/api/demo/status", { signal });
