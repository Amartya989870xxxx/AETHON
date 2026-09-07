import { clamp01 } from "../lib/format";
import { cx } from "../lib/cx";

interface Props {
  /** 0..1. */
  value: number | null | undefined;
  color?: string;
  /** Show the % label to the right. */
  showValue?: boolean;
  className?: string;
  label?: string;
}

/** Slim horizontal bar for a 0..1 score (confidence, congestion, hop score). */
export function Meter({ value, color = "#22d3ee", showValue, className, label }: Props) {
  const v = clamp01(value);
  const known = value != null && !Number.isNaN(value);
  return (
    <div className={cx("flex items-center gap-2", className)}>
      {label && <span className="w-24 shrink-0 text-xs text-ink-400">{label}</span>}
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-silk"
          style={{
            width: `${v * 100}%`,
            backgroundColor: color,
            boxShadow: known ? `0 0 8px ${color}66` : undefined,
          }}
        />
      </div>
      {showValue && (
        <span className="w-10 shrink-0 text-right text-xs tabular-nums text-ink-300">
          {known ? `${Math.round(v * 100)}%` : "—"}
        </span>
      )}
    </div>
  );
}
