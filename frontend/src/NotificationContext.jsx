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
 * Resolves the canonical event kind from a raw WebSocket event object.
 * Backend emits payloads with an "event" key (and an "event_type" from the
 * Pydantic model); legacy / test payloads may use "type" instead.
 */
function resolveEventKind(event) {
  return event.event ?? event.type ?? event.event_type ?? "";
}

/**
 * Derives the emoji icon for a given (normalised) event kind.
 */
function eventIcon(kind) {
  switch (kind) {
    case "stage_completed":            return "✅";
    case "stage_started":              return "▶️";
    case "stage_error":                return "❌";
    case "pipeline_completed":         return "🎉";
    case "pipeline_started":           return "🚀";
    case "clarification_requested":    return "❓";
    case "content_approval_requested": return "👀";
    case "image_generated":             return "🖼️";
    default:                           return "🔔";
  }
}

/**
 * Builds a human-readable fallback message for events that carry no explicit
 * "message" or "detail" field.
 */
function buildFallbackMessage(kind, stageText) {
  switch (kind) {
    case "pipeline_started":           return "Pipeline started";
    case "pipeline_completed":         return "Pipeline completed";
    case "stage_started":              return stageText ? `Started ${stageText}` : "Stage started";
    case "stage_completed":            return stageText ? `Completed ${stageText}` : "Stage completed";
    case "stage_error":                return stageText ? `Error in ${stageText}` : "Stage error";
    case "clarification_requested":    return "Clarification requested";
    case "clarification_completed":    return "Clarification completed";
    case "content_approval_requested": return "Content approval requested";
    case "content_approval_completed": return "Content approval completed";
    case "image_generated":             return "Image generated";
    case "wait_timeout":               return "Pipeline timed out waiting for input";
    default:
      return kind
        ? kind.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
        : "Notification";
  }
}

/**
 * NotificationProvider — stores the last MAX_NOTIFICATIONS pipeline events
 * and tracks which have been read.
 *
 * Provides:
 *   notifications  — array of { id, icon, stage, message, timestamp, campaignId, workspaceId, read }
 *   unreadCount    — number of unread notifications
 *   addEvent       — push a raw WebSocket event into the store
 *   markAllRead    — mark every notification as read
 *   markRead       — mark a single notification as read by id
 */
export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const seenRef = useRef(new Set());

  const addEvent = useCallback((event) => {
    const kind = resolveEventKind(event);
    const key = event.id ?? `${kind}-${event.stage ?? ""}-${event.timestamp ?? ""}`;
    if (seenRef.current.has(key)) return;
    seenRef.current.add(key);

    const stageText = stageLabel(event.stage || event.status);
    const explicitMessage = event.message || event.detail || event.error || "";

    const item = {
      id: Math.random().toString(36).slice(2),
      icon: eventIcon(kind),
      type: kind,
      stage: stageText,
      message: explicitMessage || buildFallbackMessage(kind, stageText),
      timestamp: event.timestamp || new Date().toISOString(),
      campaignId: event.campaign_id ?? null,
      workspaceId: event.workspace_id ?? null,
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
