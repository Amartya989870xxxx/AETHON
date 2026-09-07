import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import { cx } from "../lib/cx";
import { BASE_URL } from "../api/config";
import {
  AlertIcon,
  ChartIcon,
  LedgerIcon,
  MapIcon,
  RouteIcon,
  ShieldIcon,
} from "./icons";
import type { SocketStatus } from "../api/useAlertsSocket";

const NAV = [
  { to: "/map", label: "City Map", Icon: MapIcon },
  { to: "/trajectory", label: "Trajectory", Icon: RouteIcon },
  { to: "/alerts", label: "Alerts", Icon: AlertIcon },
  { to: "/analytics", label: "Analytics", Icon: ChartIcon },
  { to: "/watchlist", label: "Watch List", Icon: ShieldIcon },
  { to: "/audit", label: "Audit", Icon: LedgerIcon },
];

interface Props {
  children: ReactNode;
  socketStatus: SocketStatus;
  liveAlertCount: number;
}

export function AppShell({ children, socketStatus, liveAlertCount }: Props) {
  return (
    <div className="flex min-h-screen">
      <Sidebar liveAlertCount={liveAlertCount} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar socketStatus={socketStatus} />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-8 sm:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function Sidebar({ liveAlertCount }: { liveAlertCount: number }) {
  return (
    <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col gap-1 border-r border-white/[0.06] bg-ink-950/60 px-3 py-5 backdrop-blur-xl lg:flex">
      <Brand />
      <nav className="mt-6 flex flex-col gap-1">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cx(
                "group relative flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[13px] font-medium tracking-wide transition-all duration-300 ease-silk",
                isActive
                  ? "border-accent-400/40 bg-accent-500/[0.16] text-accent-300 shadow-[0_0_24px_rgba(34,211,238,0.22)]"
                  : "border-transparent text-ink-400 hover:border-white/10 hover:bg-white/[0.04] hover:text-ink-100",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cx(
                    "shrink-0 transition-opacity",
                    isActive ? "opacity-100" : "opacity-70 group-hover:opacity-100",
                  )}
                />
                <span className="flex-1">{label}</span>
                {to === "/alerts" && liveAlertCount > 0 && (
                  <span className="rounded-full bg-accent-500/25 px-1.5 py-0.5 text-[10px] font-semibold text-accent-300">
                    {liveAlertCount}
                  </span>
                )}
                {isActive && (
                  <motion.span
                    layoutId="nav-active-edge"
                    className="absolute inset-x-2 top-0 h-px bg-gradient-to-r from-transparent via-accent-400/70 to-transparent"
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto px-3 pt-4">
        <p className="text-[10px] leading-relaxed text-ink-600">
          Correlation layer over the city's existing ANPR network. Structured
          events only — never video.
        </p>
      </div>
    </aside>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <span className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-accent-400/50 bg-accent-500/20 shadow-[0_0_16px_rgba(34,211,238,0.25)]">
        <span className="absolute h-2 w-2 rounded-full bg-accent-300 shadow-[0_0_6px_rgba(34,211,238,0.9)]" />
        <span className="absolute h-2 w-2 animate-pulse-ring rounded-full bg-accent-400" />
      </span>
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-tight text-ink-100">
          AETHON
        </p>
        <p className="text-[10px] uppercase tracking-[0.18em] text-ink-500">
          Traffic Intel
        </p>
      </div>
    </div>
  );
}

function TopBar({ socketStatus }: { socketStatus: SocketStatus }) {
  return (
    <div className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-white/[0.06] bg-ink-950/70 px-4 backdrop-blur-xl sm:px-8">
      <div className="flex items-center gap-2 lg:hidden">
        <span className="h-1.5 w-1.5 rounded-full bg-accent-400" />
        <span className="text-sm font-semibold tracking-tight">AETHON</span>
      </div>
      <div className="hidden text-xs text-ink-500 lg:block">
        SIH 2026 · PS 26127 · Bharat Electronics Limited
      </div>
      <div className="flex items-center gap-4">
        <SocketBadge status={socketStatus} />
        <span className="hidden text-[11px] text-ink-600 sm:inline">
          {BASE_URL.replace(/^https?:\/\//, "")}
        </span>
      </div>
    </div>
  );
}

function SocketBadge({ status }: { status: SocketStatus }) {
  const map = {
    open: { color: "#4ade80", label: "Live feed" },
    connecting: { color: "#ffcc4d", label: "Connecting…" },
    closed: { color: "#5b6070", label: "Feed offline" },
  }[status];
  return (
    <span className="flex items-center gap-2 text-[11px] font-medium text-ink-300">
      <span
        className="h-2 w-2 rounded-full"
        style={{
          backgroundColor: map.color,
          boxShadow: status === "open" ? `0 0 8px ${map.color}` : undefined,
        }}
      />
      {map.label}
    </span>
  );
}

/** Bottom nav for narrow screens. */
export function MobileNav({ liveAlertCount }: { liveAlertCount: number }) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex items-stretch justify-around border-t border-white/10 bg-ink-950/85 backdrop-blur-xl lg:hidden">
      {NAV.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cx(
              "relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors",
              isActive ? "text-accent-300" : "text-ink-500",
            )
          }
        >
          <Icon width={17} height={17} />
          {label.split(" ")[0]}
          {to === "/alerts" && liveAlertCount > 0 && (
            <span className="absolute right-2 top-1 h-1.5 w-1.5 rounded-full bg-accent-400" />
          )}
        </NavLink>
      ))}
    </nav>
  );
}
