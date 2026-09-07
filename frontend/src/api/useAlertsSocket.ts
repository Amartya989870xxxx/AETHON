/**
 * Live alert feed over `WS /ws/alerts`.
 *
 * Contract (from `backend/app/api/live.py`):
 *  - server sends `{ type: "connected", at }` on open, then `{ type: "alert", ... }`
 *  - the socket is read-only from the server; the client never sends anything
 *  - only alerts from the demo driver (`POST /api/demo/start`) are broadcast;
 *    seeded / directly-posted alerts are already in `GET /api/alerts` and are
 *    NOT pushed. So this hook complements the REST list, never replaces it.
 *
 * Reconnects with backoff while `enabled`.
 */
import { useEffect, useRef, useState } from "react";
import { WS_BASE_URL } from "./config";
import type { AlertSocketMessage, SocketMessage } from "./types";

export type SocketStatus = "connecting" | "open" | "closed";

interface Options {
  enabled?: boolean;
  onAlert?: (alert: AlertSocketMessage) => void;
}

export function useAlertsSocket({ enabled = true, onAlert }: Options = {}): {
  status: SocketStatus;
  lastAlert: AlertSocketMessage | null;
} {
  const [status, setStatus] = useState<SocketStatus>("closed");
  const [lastAlert, setLastAlert] = useState<AlertSocketMessage | null>(null);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  useEffect(() => {
    if (!enabled) {
      setStatus("closed");
      return;
    }

    let ws: WebSocket | null = null;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      ws = new WebSocket(`${WS_BASE_URL}/ws/alerts`);

      ws.onopen = () => {
        retry = 0;
        setStatus("open");
      };

      ws.onmessage = (event) => {
        let msg: SocketMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        if (msg.type === "alert") {
          setLastAlert(msg);
          onAlertRef.current?.(msg);
        }
        // `connected` handshake: nothing to do.
      };

      ws.onerror = () => ws?.close();

      ws.onclose = () => {
        setStatus("closed");
        if (disposed) return;
        retry += 1;
        const delay = Math.min(1000 * 2 ** retry, 15000);
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [enabled]);

  return { status, lastAlert };
}
