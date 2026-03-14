import { useEffect, useRef, useState, useCallback } from "react";
import { getWsUrl, RateLimitError } from "../api";

/** Starting reconnect delay in milliseconds. */
const BASE_DELAY_MS = 1000;
/** Maximum reconnect delay (cap) in milliseconds. */
const MAX_DELAY_MS = 60_000;
/** Stop reconnecting after this many consecutive failures. */
const MAX_FAILURES = 10;

/**
 * Hook that connects to the backend WebSocket and accumulates events.
 * @param {string|null} campaignId — specific campaign, or null for all
 * @returns {{ events: object[], connected: boolean, connectionFailed: boolean, clear: () => void }}
 */
export default function useWebSocket(campaignId = null) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [connectionFailed, setConnectionFailed] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const connectRef = useRef(null);
  const failureCountRef = useRef(0);

  const scheduleReconnect = useCallback((delayMs) => {
    reconnectTimer.current = setTimeout(() => connectRef.current?.(), delayMs);
  }, []);

  const connect = useCallback(async () => {
    let url;
    try {
      url = await getWsUrl(campaignId);
    } catch (err) {
      console.error("Failed to obtain WS ticket:", err);
      failureCountRef.current += 1;
      if (failureCountRef.current >= MAX_FAILURES) {
        queueMicrotask(() => setConnectionFailed(true));
        return;
      }
      const delayMs =
        err instanceof RateLimitError && err.retryAfter > 0
          ? err.retryAfter * 1000
          : Math.min(BASE_DELAY_MS * 2 ** (failureCountRef.current - 1), MAX_DELAY_MS);
      scheduleReconnect(delayMs);
      return;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      failureCountRef.current = 0;
      setConnectionFailed(false);
      setConnected(true);
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents((prev) => [...prev, data]);
      } catch {
        /* ignore malformed */
      }
    };

    ws.onclose = () => {
      setConnected(false);
      failureCountRef.current += 1;
      if (failureCountRef.current >= MAX_FAILURES) {
        setConnectionFailed(true);
        return;
      }
      const delayMs = Math.min(
        BASE_DELAY_MS * 2 ** (failureCountRef.current - 1),
        MAX_DELAY_MS,
      );
      scheduleReconnect(delayMs);
    };

    ws.onerror = () => ws.close();
  }, [campaignId, scheduleReconnect]);

  // Keep ref in sync so the onclose reconnect always calls the latest version
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const clear = useCallback(() => setEvents([]), []);

  return { events, connected, connectionFailed, clear };
}
