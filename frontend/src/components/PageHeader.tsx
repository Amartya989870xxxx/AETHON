import type { ReactNode } from "react";
import { motion } from "framer-motion";

interface Props {
  title: string;
  subtitle?: string;
  /** Right-aligned controls: refresh buttons, time pickers, toggles. */
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"
    >
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink-100">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-sm text-ink-400">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      )}
    </motion.header>
  );
}
