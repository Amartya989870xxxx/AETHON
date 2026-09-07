import type { ReactNode } from "react";
import { cx } from "../lib/cx";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  /** Cell renderer. */
  cell: (row: Row) => ReactNode;
  align?: "left" | "right" | "center";
  /** Tailwind width class, e.g. "w-32". */
  width?: string;
}

interface Props<Row> {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string | number;
  onRowClick?: (row: Row) => void;
  activeKey?: string | number;
  /** Shown in place of the body when `rows` is empty. */
  empty?: ReactNode;
}

/**
 * Compact, horizontally-scrollable table. The scroll container owns
 * `overflow-x-auto` so the page body never scrolls sideways.
 */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onRowClick,
  activeKey,
  empty,
}: Props<Row>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-white/10">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cx(
                  "px-3 py-2.5 font-medium text-ink-400",
                  "text-[11px] uppercase tracking-wider",
                  col.width,
                  col.align === "right" && "text-right",
                  col.align === "center" && "text-center",
                  (!col.align || col.align === "left") && "text-left",
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3">
                {empty ?? (
                  <p className="py-10 text-center text-xs text-ink-500">
                    Nothing to show for this window.
                  </p>
                )}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => {
              const key = rowKey(row, i);
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cx(
                    "border-b border-white/5 transition-colors",
                    onRowClick && "cursor-pointer hover:bg-white/[0.04]",
                    activeKey === key && "bg-violet-500/10",
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cx(
                        "px-3 py-2.5 text-ink-200",
                        col.align === "right" && "text-right tabular-nums",
                        col.align === "center" && "text-center",
                      )}
                    >
                      {col.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
