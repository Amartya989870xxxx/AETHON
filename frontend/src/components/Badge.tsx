import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import type { EnumStyle } from "../lib/enums";

interface Props {
  style: EnumStyle;
  children?: ReactNode;
  /** Show a small filled dot before the label. */
  dot?: boolean;
  size?: "sm" | "md";
  className?: string;
}

/** A coloured enum chip driven by an `EnumStyle` from `lib/enums.ts`. */
export function Badge({ style, children, dot, size = "md", className }: Props) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap",
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        className,
      )}
      style={{
        color: style.color,
        backgroundColor: style.bg,
        borderColor: style.border,
      }}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: style.color }}
        />
      )}
      {children ?? style.label}
    </span>
  );
}
