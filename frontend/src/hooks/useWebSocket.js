import { useEffect, useRef, useState, useCallback } from "react";
import { getWsUrl } from "../api";

/**
 * Hook that connects to the backend WebSocket and accumulates events.
 * @param {string|null} campaignId — specific campaign, or null for all
 * @returns {{ events: object[], connected: boolean, clear: () => void }}
 */
export default function useWebSocket(campaignId = null) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const connectRef = useRef(null);

  const connect = useCallback(() => {
    const url = getWsUrl(campaignId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

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
      // Auto-reconnect after 3 s via ref to avoid accessing connect before declaration
      reconnectTimer.current = setTimeout(() => connectRef.current?.(), 3000);
    };

    ws.onerror = () => ws.close();
  }, [campaignId]);

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

  return { events, connected, clear };
}
