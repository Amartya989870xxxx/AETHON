/**
 * Response contracts, transcribed from the AETHON backend source
 * (`backend/app/schemas.py`, `backend/app/api/*`, `backend/app/engines/*`).
 *
 * Rules baked in here:
 *  - GeoJSON `coordinates` are `[lon, lat]` (see `lib/geo.ts` for the swap).
 *  - Every timestamp is an ISO-8601 string in UTC (some without a `Z` suffix);
 *    render through `lib/datetime.ts`, never `new Date(x).toString()`.
 *  - `confidence` / `*_score` values are 0..1, never a percentage.
 *  - Fields typed `| null` really can be null — design an empty state.
 */

// --- GeoJSON ----------------------------------------------------------------

export interface GeoPoint {
  type: "Point";
  /** [longitude, latitude] — GeoJSON order. */
  coordinates: [number, number];
}

export interface Feature<P> {
  type: "Feature";
  geometry: GeoPoint;
  properties: P;
}

export interface FeatureCollection<P> {
  type: "FeatureCollection";
  features: Feature<P>[];
  window?: TimeWindow;
}

export interface TimeWindow {
  start: string;
  end: string;
}

// --- Cameras (GET /api/cameras) -------------------------------------------

export interface CameraProps {
  camera_id: string;
  name: string;
  road_segment: string;
  zone: string;
  facing_direction: string;
  lanes: number;
  is_restricted: boolean;
  active: boolean;
}

export type CameraCollection = FeatureCollection<CameraProps>;

// --- Heatmap (GET /api/analytics/heatmap) -------------------------------

export interface HeatmapProps {
  camera_id: string;
  camera_name: string;
  road_segment: string;
  zone: string;
  vehicle_count: number;
  avg_speed_kmph: number | null;
  density_per_lane: number | null;
  congestion_score: number;
  z_score: number | null;
  is_congested: boolean;
  bucket_start: string;
}

export type HeatmapCollection = FeatureCollection<HeatmapProps>;

// --- Plate search (GET /api/plates/search) ------------------------------

export interface PlateMatch {
  plate: string;
  sightings: number;
  cameras: string[];
  vehicle_types: string[];
  first_seen: string;
  last_seen: string;
  best_confidence: number;
}

export interface PlateSearchResponse {
  query: string;
  matches: PlateMatch[];
  total_matches: number;
}

// --- Trajectory (GET /api/trajectory/{plate}) --------------------------

export type MatchKind = "exact" | `fuzzy(d=${number})`;

export interface PathNode {
  observation_id: number;
  camera_id: string;
  camera_name: string;
  lat: number | null;
  lon: number | null;
  zone: string | null;
  road_segment: string | null;
  timestamp: string;
  direction: string;
  confidence: number;
  vehicle_type: string;
  condition: string;
  plate_read: string;
  edit_distance: number;
  match: MatchKind;
}

export interface Hop {
  from_index: number;
  to_index: number;
  seconds: number;
  distance_km: number;
  implied_speed_kmph: number;
  hops_on_graph: number;
  time_score: number;
  direction_score: number;
  ocr_score: number;
  total: number;
  /** Cameras the engine bridged over — non-empty means "gap filled here". */
  intermediate_cameras: string[];
}

export interface RejectedHop {
  from_camera: string;
  to_camera: string;
  from_ts: string;
  to_ts: string;
  reason: string;
  detail: Record<string, unknown>;
}

export interface TrajectoryResponse {
  plate: string;
  found: boolean;
  score: number;
  path: PathNode[];
  hops: Hop[];
  rejected: RejectedHop[];
  total_distance_km: number;
  duration_seconds: number;
  candidates_considered: number;
  fuzzy_used: boolean;
  note: string;
}

// --- Alerts (GET /api/alerts) -----------------------------------------

export type AlertType =
  | "blacklist_hit"
  | "blacklist_possible"
  | "impossible_travel"
  | "restricted_zone"
  | "loitering"
  | "odd_hours";

export type Severity = "critical" | "high" | "medium" | "low";
export type AlertStatus = "open" | "acknowledged" | "dismissed";

export interface Alert {
  id: number;
  alert_type: AlertType | string;
  severity: Severity | string;
  plate_norm: string;
  camera_id: string | null;
  observation_id: number | null;
  confidence: number;
  status: AlertStatus | string;
  title: string;
  /** Free-form; shape varies by alert_type. Render generically. */
  evidence: Record<string, unknown>;
  created_at: string;
  acknowledged_by: string | null;
}

export interface AlertStats {
  total: number;
  open: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  reviewed: number;
  false_positive_rate: number | null;
}

export type Disposition = "confirmed" | "false_positive" | "escalated";

export interface AcknowledgeBody {
  actor: string;
  disposition: Disposition;
  note?: string;
}

/** Message shape pushed over WS /ws/alerts (type === "alert"). */
export interface AlertSocketMessage {
  type: "alert";
  id: number;
  alert_type: AlertType | string;
  severity: Severity | string;
  plate: string;
  camera_id: string | null;
  title: string;
  confidence: number;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface ConnectedSocketMessage {
  type: "connected";
  at: string;
}

export type SocketMessage = AlertSocketMessage | ConnectedSocketMessage;

// --- Analytics --------------------------------------------------------

export interface BottleneckRow {
  road_segment: string;
  buckets_observed: number;
  buckets_congested: number;
  congested_share: number;
  avg_congestion_score: number;
  avg_speed_kmph: number | null;
  total_vehicles: number;
}

export interface BottlenecksResponse {
  window: TimeWindow;
  bottlenecks: BottleneckRow[];
}

export interface AnalyticsSummary {
  generated_at: string;
  live_window_minutes: number;
  cameras_reporting: number;
  vehicles_in_window: number;
  congested_cameras: string[];
  mean_speed_kmph: number | null;
  top_bottlenecks: BottleneckRow[];
}

export interface ODMatrix {
  zones: string[];
  matrix: Record<string, Record<string, number>>;
  avg_duration_s: Record<string, number>;
  window: TimeWindow;
}

export interface SegmentPoint {
  bucket_start: string;
  vehicle_count: number;
  avg_speed_kmph: number | null;
  congestion_score: number;
}

export interface SegmentSeriesResponse {
  road_segment: string;
  series: SegmentPoint[];
}

// --- Watch list (GET/POST/DELETE /api/blacklist) --------------------

export interface BlacklistEntry {
  id: number;
  plate_norm: string;
  reason: string;
  severity: Severity | string;
  added_by: string;
  added_at: string;
  active: boolean;
}

export interface BlacklistBody {
  plate_text: string;
  reason: string;
  severity?: Severity | string;
  added_by?: string;
}

// --- Audit (GET /api/audit) ---------------------------------------

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  subject: string;
  detail: Record<string, unknown>;
}

export interface AuditResponse {
  entries: AuditEntry[];
  count: number;
}

// --- Observations (GET/POST /api/observations) ------------------

export interface Observation {
  id: number;
  camera_id: string;
  ts: string;
  plate_text: string;
  plate_norm: string;
  plate_confidence: number;
  vehicle_type: string;
  direction: string;
  lane: number;
  speed_estimate_kmph: number | null;
  frames_fused: number;
  format_valid: boolean;
  repairs: unknown[];
  condition: string;
  frame_ref: string | null;
}

export interface ObservationBody {
  camera_id: string;
  timestamp: string;
  plate_text: string;
  plate_confidence: number;
  vehicle_type?: string;
  direction?: string;
  lane?: number;
  speed_estimate_kmph?: number | null;
  condition?: string;
  frames_fused?: number;
  frame_ref?: string | null;
}

export interface IngestResult {
  observation_id: number;
  plate_norm: string;
  format_valid: boolean;
  repairs: unknown[];
  alerts_raised: {
    id: number;
    type: string;
    severity: string;
    title: string;
  }[];
}

// --- Demo driver ---------------------------------------------------

export interface DemoStatus {
  running: boolean;
  events_sent: number;
  alerts_raised: number;
  dashboard_clients?: number;
}
