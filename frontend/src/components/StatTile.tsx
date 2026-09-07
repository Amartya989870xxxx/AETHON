import type { ReactNode } from "react";
import { GlassPanel } from "./GlassPanel";
import { cx } from "../lib/cx";

interface Props {
  label: string;
  value: ReactNode;
  /** Sub-line under the value — units, context, or an empty-state note. */
  hint?: ReactNode;
  accent?: string;
  icon?: ReactNode;
  /** Dim the tile + swap the value for a muted "no data" treatment. */
  empty?: boolean;
}

/**
 * Header KPI tile. Used across summary rows on every screen. The enter
 * animation is pure CSS (`animate-fade-up`, `both` fill) so the content is
 * never left stuck at opacity 0 if a frame is dropped.
 */
export function StatTile({ label, value, hint, accent, icon, empty }: Props) {
  return (
    <div className="animate-fade-up">
      <GlassPanel interactive className="h-full">
        <div className="flex items-start justify-between gap-3">
          <span className="eyebrow">{label}</span>
          {icon && <span className="text-ink-400">{icon}</span>}
        </div>
        <div
          className={cx(
            "mt-3 text-2xl font-semibold tracking-tight tabular-nums",
            empty ? "text-ink-400" : "text-ink-100",
          )}
          style={!empty && accent ? { color: accent } : undefined}
        >
          {empty ? "—" : value}
        </div>
        {hint && (
          <div className="mt-1 text-xs text-ink-400">
            {empty ? "not enough data yet" : hint}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
