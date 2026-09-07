import { useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { GlassPanel } from "../components/GlassPanel";
import { Badge } from "../components/Badge";
import { Button, Field, Select, TextInput } from "../components/controls";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorState, SkeletonRows } from "../components/states";
import { RefreshIcon } from "../components/icons";
import { useApi } from "../hooks/useApi";
import { useToast } from "../components/toast";
import { addBlacklist, getBlacklist, removeBlacklist } from "../api/endpoints";
import { OPERATOR_NAME } from "../api/config";
import { SEVERITY_STYLE, lookupStyle } from "../lib/enums";
import { formatLocal } from "../lib/datetime";
import type { BlacklistEntry } from "../api/types";

export function WatchlistScreen() {
  const [activeOnly, setActiveOnly] = useState(true);
  const toast = useToast();
  const list = useApi(
    (signal) => getBlacklist(activeOnly, signal),
    [activeOnly],
  );

  const [plate, setPlate] = useState("");
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState("high");
  const [addedBy, setAddedBy] = useState(OPERATOR_NAME);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!plate.trim() || !reason.trim()) return;
    setBusy(true);
    try {
      const entry = await addBlacklist({
        plate_text: plate.trim(),
        reason: reason.trim(),
        severity,
        added_by: addedBy.trim() || OPERATOR_NAME,
      });
      toast.push({
        kind: "success",
        title: "Added to watch list",
        body: `${entry.plate_norm} — live for the next observation.`,
      });
      setPlate("");
      setReason("");
      list.refetch();
    } catch (err) {
      toast.push({
        kind: "error",
        title: "Couldn't add entry",
        body: (err as Error).message,
      });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (entry: BlacklistEntry) => {
    try {
      await removeBlacklist(entry.plate_norm);
      toast.push({ kind: "info", title: `${entry.plate_norm} removed` });
      list.refetch();
    } catch (err) {
      toast.push({
        kind: "error",
        title: "Couldn't remove entry",
        body: (err as Error).message,
      });
    }
  };

  const columns: Column<BlacklistEntry>[] = [
    {
      key: "plate",
      header: "Plate",
      cell: (e) => (
        <span className="font-mono text-ink-100">{e.plate_norm}</span>
      ),
    },
    {
      key: "reason",
      header: "Reason",
      cell: (e) => <span className="text-ink-200">{e.reason}</span>,
    },
    {
      key: "sev",
      header: "Severity",
      cell: (e) => (
        <Badge size="sm" dot style={lookupStyle(SEVERITY_STYLE, e.severity)} />
      ),
    },
    {
      key: "by",
      header: "Added by",
      cell: (e) => <span className="text-ink-400">{e.added_by}</span>,
    },
    {
      key: "at",
      header: "Added",
      align: "right",
      cell: (e) => (
        <span className="text-ink-400">{formatLocal(e.added_at)}</span>
      ),
    },
    {
      key: "act",
      header: "",
      align: "right",
      cell: (e) =>
        e.active ? (
          <Button size="sm" variant="danger" onClick={() => remove(e)}>
            Remove
          </Button>
        ) : (
          <span className="text-[11px] text-ink-600">inactive</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Watch list"
        subtitle="Plates that raise an alert on their next sighting anywhere in the network"
        actions={
          <Button
            size="sm"
            icon={<RefreshIcon />}
            onClick={() => list.refetch()}
            loading={list.loading && !list.initial}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <GlassPanel>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="eyebrow">
              {list.data?.length ?? 0} {activeOnly ? "active" : "total"} entries
            </h3>
            <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-400">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
                className="accent-accent-500"
              />
              active only
            </label>
          </div>

          {list.error ? (
            <ErrorState error={list.error} bare onRetry={list.refetch} />
          ) : list.initial ? (
            <SkeletonRows rows={6} />
          ) : (
            <DataTable
              columns={columns}
              rows={list.data ?? []}
              rowKey={(e) => e.id}
              empty={
                <p className="py-8 text-center text-xs text-ink-500">
                  The watch list is empty.
                </p>
              }
            />
          )}
        </GlassPanel>

        <GlassPanel>
          <h3 className="eyebrow mb-3">Add entry</h3>
          <div className="space-y-3">
            <Field label="Plate" hint="Sent as-is — the backend normalises it.">
              <TextInput
                value={plate}
                onChange={(e) => setPlate(e.target.value.toUpperCase())}
                placeholder="KA05MG2345"
                className="font-mono"
              />
            </Field>
            <Field label="Reason">
              <TextInput
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Stolen vehicle report #…"
              />
            </Field>
            <Field label="Severity">
              <Select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                {Object.keys(SEVERITY_STYLE).map((s) => (
                  <option key={s} value={s}>
                    {SEVERITY_STYLE[s].label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Added by"
              hint="Free text — there is no user session yet."
            >
              <TextInput
                value={addedBy}
                onChange={(e) => setAddedBy(e.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              className="w-full"
              loading={busy}
              disabled={!plate.trim() || !reason.trim()}
              onClick={submit}
            >
              Add to watch list
            </Button>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
