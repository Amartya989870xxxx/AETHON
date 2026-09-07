import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { cx } from "../lib/cx";
import { Spinner } from "./states";

/* ----------------------------------------------------------------- Button */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "ghost",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-all duration-300 ease-silk",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" &&
          "border-accent-500/50 bg-accent-500/15 text-accent-400 hover:border-accent-400 hover:bg-accent-500/25 hover:text-white hover:shadow-glow",
        variant === "ghost" &&
          "border-white/10 bg-white/5 text-ink-200 hover:border-accent-500/40 hover:text-white",
        variant === "danger" &&
          "border-signal-critical/40 bg-signal-critical/10 text-signal-critical hover:border-signal-critical/70 hover:bg-signal-critical/20",
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="h-3.5 w-3.5" /> : icon}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ Field */

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="eyebrow">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-ink-500">{hint}</span>}
    </label>
  );
}

const inputBase =
  "w-full rounded-lg border border-white/10 bg-ink-900/70 px-3 py-2 text-sm text-ink-100 outline-none transition placeholder:text-ink-500 focus:border-accent-500/60 focus:bg-ink-900 focus:ring-2 focus:ring-accent-500/20";

export function TextInput({
  className,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(inputBase, className)} {...rest} />;
}

export function Select({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(inputBase, "appearance-none pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

/* --------------------------------------------------------------- SegButton */

interface SegProps<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: SegProps<T>) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 bg-ink-900/60 p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cx(
            "rounded-[7px] px-3 py-1.5 text-xs font-medium transition-all duration-300 ease-silk",
            value === opt.value
              ? "bg-accent-500/20 text-white shadow-glow"
              : "text-ink-400 hover:text-ink-200",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
