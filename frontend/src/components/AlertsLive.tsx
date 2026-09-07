import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAlertsSocket, type SocketStatus } from "../api/useAlertsSocket";
import type { AlertSocketMessage } from "../api/types";
import { useToast } from "./toast";
import { lookupStyle, ALERT_TYPE_STYLE } from "../lib/enums";

interface AlertsLiveShape {
  status: SocketStatus;
  /** Alerts received via WS this session, newest first. */
  liveAlerts: AlertSocketMessage[];
  /** Clear the "new since you last looked" counter. */
  markSeen: () => void;
  unseenCount: number;
}

const AlertsLiveContext = createContext<AlertsLiveShape | null>(null);

/**
 * One WebSocket for the whole app. The nav badge and the Alerts screen both
 * read from here, so we never open two sockets. New alerts also raise a toast.
 */
export function AlertsLiveProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [liveAlerts, setLiveAlerts] = useState<AlertSocketMessage[]>([]);
  const [seenId, setSeenId] = useState<number>(0);

  const onAlert = useCallback(
    (alert: AlertSocketMessage) => {
      setLiveAlerts((prev) =>
        prev.some((a) => a.id === alert.id) ? prev : [alert, ...prev].slice(0, 200),
      );
      toast.push({
        kind: "alert",
        title: lookupStyle(ALERT_TYPE_STYLE, alert.alert_type).label,
        body: alert.title,
      });
    },
    [toast],
  );

  const { status } = useAlertsSocket({ onAlert });

  const markSeen = useCallback(() => {
    setLiveAlerts((prev) => {
      if (prev[0]) setSeenId(prev[0].id);
      return prev;
    });
  }, []);

  const unseenCount = useMemo(
    () => liveAlerts.filter((a) => a.id > seenId).length,
    [liveAlerts, seenId],
  );

  const value = useMemo<AlertsLiveShape>(
    () => ({ status, liveAlerts, markSeen, unseenCount }),
    [status, liveAlerts, markSeen, unseenCount],
  );

  return (
    <AlertsLiveContext.Provider value={value}>
      {children}
    </AlertsLiveContext.Provider>
  );
}

export function useAlertsLive(): AlertsLiveShape {
  const ctx = useContext(AlertsLiveContext);
  if (!ctx) throw new Error("useAlertsLive must be used inside AlertsLiveProvider");
  return ctx;
}
