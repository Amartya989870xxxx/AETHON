import { useMemo, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { Button, TextInput } from "../components/controls";
import { DataTable, type Column } from "../components/DataTable";
import { KeyValueList } from "../components/KeyValueList";
import { ErrorState, SkeletonRows } from "../components/states";
import { RefreshIcon } from "../components/icons";
import { TimeWindowPicker, useWindowParams } from "../components/TimeWindow";
import { useApi } from "../hooks/useApi";
import { getAudit } from "../api/endpoints";
import { humanize } from "../lib/format";
import { formatLocal } from "../lib/datetime";
import type { AuditEntry } from "../api/types";

const ACTION_COLORS: Record<string, string> = {
  trajectory_query: "#d946ef",
  alert_acknowledged: "#4ade80",
  blacklist_add: "#ff8f4c",
  blacklist_remove: "#5b6070",
};

export function AuditScreen() {
  const win = useWindowParams();
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [subject, setSubject] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const audit = useApi(
    (signal) =>
      getAudit(
        {
          ...win,
          actor: actor || undefined,
          action: action || undefined,
          subject: subject || undefined,
          limit: 500,
        },
        signal,
      ),
    [win.start, win.end, actor, action, subject],
  );

  const rows = audit.data?.entries ?? [];

  const columns: Column<AuditEntry>[] = useMemo(
    () => [
      {
        key: "ts",
        header: "When",
        width: "w-44",
        cell: (e) => (
          <span className="text-ink-300">{formatLocal(e.ts)}</span>
        ),
      },
      {
        key: "actor",
        header: "Actor",
        cell: (e) => <span className="text-ink-200">{e.actor}</span>,
      },
      {
        key: "action",
        header: "Action",
        cell: (e) => (
          <span
            className="rounded px-1.5 py-0.5 text-[11px] font-medium"
            style={{
              color: ACTION_COLORS[e.action] ?? "#8b90a0",
              background: `${ACTION_COLORS[e.action] ?? "#8b90a0"}1f`,
            }}
          >
            {humanize(e.action)}
          </span>
        ),
      },
      {
        key: "subject",
        header: "Subject",
        cell: (e) => (
          <span className="font-mono text-ink-300">{e.subject || "—"}</span>
        ),
      },
      {
        key: "detail",
        header: "",
        align: "right",
        cell: (e) =>
          Object.keys(e.detail).length > 0 ? (
            <button
              onClick={() => setExpanded(expanded === e.id ? null : e.id)}
              className="text-[11px] text-violet-400 hover:text-violet-300"
            >
              {expanded === e.id ? "hide" : "detail"}
            </button>
          ) : null,
      },
    ],
    [expanded],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit log"
        subtitle="Who looked up whom, and which alerts were actioned — a city plate reader is a surveillance capability, and this makes its use reviewable"
        actions={
          <>
            <TimeWindowPicker />
            <Button
              size="sm"
              icon={<RefreshIcon />}
              onClick={() => audit.refetch()}
              loading={audit.loading && !audit.initial}
            >
              Refresh
            </Button>
          </>
        }
      />

      <GlassPanel>
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          <TextInput
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Filter by actor"
          />
          <TextInput
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="Filter by action (e.g. trajectory_query)"
          />
          <TextInput
            value={subject}
            onChange={(e) => setSubject(e.target.value.toUpperCase())}
            placeholder="Filter by subject / plate"
            className="font-mono"
          />
        </div>

        {audit.error ? (
          <ErrorState error={audit.error} bare onRetry={audit.refetch} />
        ) : audit.initial ? (
          <SkeletonRows rows={10} />
        ) : (
          <>
            <p className="mb-2 text-xs text-ink-500">
              {audit.data?.count ?? 0} entries in window
            </p>
            <DataTable
              columns={columns}
              rows={rows}
              rowKey={(e) => e.id}
              activeKey={expanded ?? undefined}
              empty={
                <p className="py-8 text-center text-xs text-ink-500">
                  No audit entries match these filters.
                </p>
              }
            />
            {expanded != null &&
              (() => {
                const entry = rows.find((e) => e.id === expanded);
                if (!entry) return null;
                return (
                  <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                    <p className="eyebrow mb-2">
                      Detail · entry #{entry.id}
                    </p>
                    <KeyValueList data={entry.detail} />
                  </div>
                );
              })()}
          </>
        )}
      </GlassPanel>
    </div>
  );
}
