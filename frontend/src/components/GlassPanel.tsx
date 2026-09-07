import { forwardRef, type HTMLAttributes } from "react";
import { cx } from "../lib/cx";

type Props = HTMLAttributes<HTMLDivElement> & {
  /** Adds the accent-glow hover lift. */
  interactive?: boolean;
  /** Removes default padding (for maps / tables that bleed to the edge). */
  flush?: boolean;
};

/**
 * The core surface. Frosted glass with an illuminated top edge, lifted from
 * the Argus dock capsule (`Nav.module.css`).
 */
export const GlassPanel = forwardRef<HTMLDivElement, Props>(function GlassPanel(
  { interactive, flush, className, children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cx(
        "glass",
        interactive && "glass-hover",
        !flush && "p-5",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
});
