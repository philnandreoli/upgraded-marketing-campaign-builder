import { createContext, useCallback, useContext, useState, useRef } from "react";

const NotificationContext = createContext(null);

/** Maximum number of notifications to keep in history. */
const MAX_NOTIFICATIONS = 20;

/**
 * Derives a human-readable label from a pipeline stage key / status string.
 */
function stageLabel(stage) {
  if (!stage) return "";
  return stage
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Derives the emoji icon for a given event type.
 */
function eventIcon(type) {
  switch (type) {
    case "stage_complete": return "✅";
    case "stage_start":   return "▶️";
    case "stage_error":   return "❌";
    case "pipeline_complete": return "🎉";
    case "clarification_needed": return "❓";
    case "content_approval_needed": return "👀";
    default: return "🔔";
  }
}

/**
 * NotificationProvider — stores the last MAX_NOTIFICATIONS pipeline events
 * and tracks which have been read.
 *
 * Provides:
 *   notifications  — array of { id, icon, stage, message, timestamp, read }
 *   unreadCount    — number of unread notifications
 *   addEvent       — push a raw WebSocket event into the store
 *   markAllRead    — mark every notification as read
 *   markRead       — mark a single notification as read by id
 */
export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const seenRef = useRef(new Set());

  const addEvent = useCallback((event) => {
    const key = event.id ?? `${event.type}-${event.stage}-${event.timestamp}`;
    if (seenRef.current.has(key)) return;
    seenRef.current.add(key);

    const item = {
      id: Math.random().toString(36).slice(2),
      icon: eventIcon(event.type),
      type: event.type,
      stage: stageLabel(event.stage || event.status),
      message: event.message || event.detail || "",
      timestamp: event.timestamp || new Date().toISOString(),
      read: false,
    };

    setNotifications((prev) => [item, ...prev].slice(0, MAX_NOTIFICATIONS));
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const markRead = useCallback((id) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <NotificationContext.Provider
      value={{ notifications, unreadCount, addEvent, markAllRead, markRead }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

/**
 * useNotifications — access notification state and actions.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationProvider");
  return ctx;
}
