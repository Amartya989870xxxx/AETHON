import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { StatTile } from "../components/StatTile";
import { Badge } from "../components/Badge";
import { Button, Field, Select, TextInput } from "../components/controls";
import { EmptyState, ErrorState, SkeletonRows } from "../components/states";
import { KeyValueList } from "../components/KeyValueList";
import { PlayIcon, RefreshIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useAlertsLive } from "../components/AlertsLive";
import { useToast } from "../components/toast";
import {
  acknowledgeAlert,
  getAlertStats,
  getAlerts,
  startDemo,
} from "../api/endpoints";
import { OPERATOR_NAME } from "../api/config";
import {
  ALERT_STATUS_STYLE,
  ALERT_TYPE_STYLE,
  SEVERITY_STYLE,
  lookupStyle,
} from "../lib/enums";
import { pct } from "../lib/format";
import { formatLocal, formatRelative } from "../lib/datetime";
import type { Alert, AlertStats, Disposition } from "../api/types";

const STATUS_OPTIONS = ["open", "acknowledged", "dismissed", "all"] as const;

/** Common display row — the REST `Alert` and the WS message unify to this. */
interface Row {
  id: number;
  alert_type: string;
  severity: string;
  plate: string;
  camera_id: string | null;
  confidence: number;
  status: string;
  title: string;
  evidence: Record<string, unknown>;
  created_at: string;
  acknowledged_by: string | null;
  live: boolean;
}

function fromAlert(a: Alert): Row {
  return { ...a, plate: a.plate_norm, live: false };
}

export function AlertsScreen() {
  const [status, setStatus] = useState<(typeof STATUS_OPTIONS)[number]>("open");
  const [severity, setSeverity] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const toast = useToast();
  const { liveAlerts, markSeen, status: socketStatus } = useAlertsLive();

  useEffect(() => {
    markSeen();
  }, [markSeen]);

  const list = useApi(
    (signal) =>
      getAlerts(
        {
          status: status === "all" ? undefined : status,
          severity: severity || undefined,
          limit: 200,
        },
        signal,
      ),
    [status, severity],
  );

  const stats = useApi((signal) => getAlertStats(signal), []);

  // Merge live (WS) alerts on top of the REST list, de-duped by id. Live
  // alerts have no status from the socket, so they show as `open` and pass
  // the "open"/"all" filters.
  const rows = useMemo<Row[]>(() => {
    const rest = (list.data ?? []).map(fromAlert);
    const restIds = new Set(rest.map((r) => r.id));
    const live: Row[] = liveAlerts
      .filter((a) => !restIds.has(a.id))
      .filter(() => status === "open" || status === "all")
      .filter((a) => !severity || a.severity === severity)
      .map((a) => ({
        id: a.id,
        alert_type: a.alert_type,
        severity: a.severity,
        plate: a.plate,
        camera_id: a.camera_id,
        confidence: a.confidence,
        status: "open",
        title: a.title,
        evidence: a.evidence,
        created_at: a.created_at,
        acknowledged_by: null,
        live: true,
      }));
    return [...live, ...rest];
  }, [list.data, liveAlerts, status, severity]);

  const selected = rows.find((r) => r.id === selectedId) ?? null;

  const onAck = async (
    id: number,
    body: { actor: string; disposition: Disposition; note: string },
  ) => {
    try {
      await acknowledgeAlert(id, body);
      toast.push({
        kind: "success",
        title: "Alert updated",
        body:
          body.disposition === "false_positive"
            ? "Marked as false positive (dismissed)."
            : `Acknowledged (${body.disposition}).`,
      });
      list.refetch();
      stats.refetch();
      setSelectedId(null);
    } catch (err) {
      toast.push({
        kind: "error",
        title: "Couldn't update alert",
        body: (err as Error).message,
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts"
        subtitle="Watch-list hits and route anomalies — live feed plus history"
        actions={
          <>
            {import.meta.env.DEV && (
              <Button
                size="sm"
                variant="primary"
                icon={<PlayIcon width={13} height={13} />}
                onClick={async () => {
                  try {
                    await startDemo(120, 60);
                    toast.push({
                      kind: "info",
                      title: "Demo driver started",
                      body: "Simulated traffic is now streaming alerts over the socket for ~2 min.",
                    });
                  } catch (err) {
                    toast.push({
                      kind: "error",
                      title: "Couldn't start demo",
                      body: (err as Error).message,
                    });
                  }
                }}
              >
                Start live demo
              </Button>
            )}
            <Button
              size="sm"
              icon={<RefreshIcon />}
              onClick={() => {
                list.refetch();
                stats.refetch();
              }}
              loading={list.loading && !list.initial}
            >
              Refresh
            </Button>
          </>
        }
      />

      <StatsRow stats={stats.data} loading={stats.initial} />

      <div className="grid gap-6 lg:grid-cols-[1fr_minmax(320px,380px)]">
        <GlassPanel>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 bg-ink-900/60 p-0.5">
              {STATUS_OPTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  className={`rounded-[7px] px-3 py-1.5 text-xs font-medium capitalize transition ${
                    status === s
                      ? "bg-violet-500/20 text-white"
                      : "text-ink-400 hover:text-ink-200"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <Select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="w-auto"
            >
              <option value="">All severities</option>
              {Object.keys(SEVERITY_STYLE).map((s) => (
                <option key={s} value={s}>
                  {SEVERITY_STYLE[s].label}
                </option>
              ))}
            </Select>
            {socketStatus === "open" && (
              <span className="ml-auto flex items-center gap-1.5 text-[11px] text-signal-ok">
                <span className="h-1.5 w-1.5 rounded-full bg-signal-ok" />
                live
              </span>
            )}
          </div>

          {list.error ? (
            <ErrorState error={list.error} bare onRetry={list.refetch} />
          ) : list.initial ? (
            <SkeletonRows rows={8} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No alerts here"
              message={
                status === "open"
                  ? "Nothing open right now. New alerts from the demo driver appear here live."
                  : `No ${status} alerts.`
              }
            />
          ) : (
            <ul className="space-y-1.5">
              <AnimatePresence initial={false}>
                {rows.map((r) => (
                  <motion.li
                    key={r.id}
                    layout
                    initial={false}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <div className={r.live ? "animate-fade-down" : undefined}>
                      <AlertRow
                        row={r}
                        active={r.id === selectedId}
                        onClick={() =>
                          setSelectedId(r.id === selectedId ? null : r.id)
                        }
                      />
                    </div>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </GlassPanel>

        <div className="lg:sticky lg:top-20 lg:self-start">
          {selected ? (
            <AlertDetail row={selected} onAck={onAck} />
          ) : (
            <GlassPanel>
              <EmptyState
                title="Select an alert"
                message="Pick a row to see its evidence and record a disposition."
              />
            </GlassPanel>
          )}
        </div>
      </div>
    </div>
  );
}

function StatsRow({
  stats,
  loading,
}: {
  stats: AlertStats | undefined;
  loading: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatTile
        label="Total alerts"
        value={loading ? "…" : (stats?.total ?? 0)}
      />
      <StatTile
        label="Open"
        value={loading ? "…" : (stats?.open ?? 0)}
        accent={stats?.open ? "#8b5cf6" : undefined}
      />
      <StatTile
        label="Reviewed"
        value={loading ? "…" : (stats?.reviewed ?? 0)}
      />
      <StatTile
        label="False-positive rate"
        value={pct(stats?.false_positive_rate, 1)}
        empty={!stats || stats.false_positive_rate == null}
        hint="dismissed ÷ reviewed"
      />
    </div>
  );
}

function AlertRow({
  row,
  active,
  onClick,
}: {
  row: Row;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg border px-3 py-2.5 text-left transition-all duration-300 ease-silk ${
        active
          ? "border-violet-500/50 bg-violet-500/10"
          : "border-white/[0.06] bg-white/[0.02] hover:border-violet-500/30 hover:bg-white/[0.04]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge
              size="sm"
              dot
              style={lookupStyle(SEVERITY_STYLE, row.severity)}
            />
            <Badge
              size="sm"
              style={lookupStyle(ALERT_TYPE_STYLE, row.alert_type)}
            />
            {row.live && (
              <span className="rounded-full bg-signal-ok/15 px-1.5 py-0.5 text-[10px] font-semibold text-signal-ok">
                LIVE
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-sm text-ink-100">{row.title}</p>
          <p className="mt-0.5 text-[11px] text-ink-400">
            <span className="font-mono text-ink-300">{row.plate}</span>
            {row.camera_id && ` · ${row.camera_id}`} ·{" "}
            {formatRelative(row.created_at)}
          </p>
        </div>
        <Badge
          size="sm"
          style={lookupStyle(ALERT_STATUS_STYLE, row.status)}
        />
      </div>
    </button>
  );
}

function AlertDetail({
  row,
  onAck,
}: {
  row: Row;
  onAck: (
    id: number,
    body: { actor: string; disposition: Disposition; note: string },
  ) => void;
}) {
  const [actor, setActor] = useState(OPERATOR_NAME);
  const [disposition, setDisposition] = useState<Disposition>("confirmed");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const canAck = row.status === "open";

  return (
    <GlassPanel>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap gap-1.5">
            <Badge size="sm" dot style={lookupStyle(SEVERITY_STYLE, row.severity)} />
            <Badge size="sm" style={lookupStyle(ALERT_TYPE_STYLE, row.alert_type)} />
          </div>
          <h3 className="mt-2 text-sm font-semibold text-ink-100">
            {row.title}
          </h3>
          <p className="mt-1 text-[11px] text-ink-500">
            #{row.id} · <span className="font-mono">{row.plate}</span>
            {row.camera_id && ` · ${row.camera_id}`} · conf {pct(row.confidence)}
          </p>
          <p className="text-[11px] text-ink-500">{formatLocal(row.created_at)}</p>
        </div>
        <Badge style={lookupStyle(ALERT_STATUS_STYLE, row.status)} />
      </div>

      <div className="mt-4">
        <p className="eyebrow mb-2">Evidence</p>
        <KeyValueList data={row.evidence} />
      </div>

      <div className="mt-5 border-t border-white/[0.06] pt-4">
        <p className="eyebrow mb-3">Record disposition</p>
        {!canAck ? (
          <p className="text-xs text-ink-500">
            Already {row.status}
            {row.acknowledged_by ? ` by ${row.acknowledged_by}` : ""}.
          </p>
        ) : row.live ? (
          <p className="text-xs text-ink-500">
            This alert just arrived over the socket. Refresh the list to load it
            from the database, then record a disposition.
          </p>
        ) : (
          <div className="space-y-3">
            <Field label="Operator">
              <TextInput
                value={actor}
                onChange={(e) => setActor(e.target.value)}
              />
            </Field>
            <Field label="Disposition">
              <Select
                value={disposition}
                onChange={(e) =>
                  setDisposition(e.target.value as Disposition)
                }
              >
                <option value="confirmed">Confirmed</option>
                <option value="false_positive">
                  False positive (dismisses)
                </option>
                <option value="escalated">Escalated</option>
              </Select>
            </Field>
            <Field label="Note (optional)">
              <TextInput
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Context for the audit trail"
              />
            </Field>
            <Button
              variant={
                disposition === "false_positive" ? "danger" : "primary"
              }
              loading={busy}
              onClick={async () => {
                setBusy(true);
                await onAck(row.id, { actor, disposition, note });
                setBusy(false);
              }}
              className="w-full"
            >
              {disposition === "false_positive"
                ? "Mark false positive"
                : "Acknowledge"}
            </Button>
            <p className="text-[10px] leading-relaxed text-ink-600">
              “False positive” is the only disposition that feeds the
              false-positive rate — use it deliberately, not as a generic
              dismiss.
            </p>
          </div>
        )}
      </div>
    </GlassPanel>
  );
}
