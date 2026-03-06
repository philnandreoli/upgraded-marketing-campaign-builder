import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";

const DISPLAY_MS = 3500;
const EXIT_MS = 200;

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
 * Toast — renders auto-dismissing notifications for WebSocket pipeline events.
 *
 * Props:
 *   events  — array of WebSocket event objects from useWebSocket
 */
export default function Toast({ events }) {
  const [toasts, setToasts] = useState([]);
  const seenRef = useRef(new Set());
  const timersRef = useRef({});

  useEffect(() => {
    if (!events || events.length === 0) return;

    // Only process events we haven't shown yet
    const newEvents = events.filter((e) => {
      const key = e.id ?? `${e.type}-${e.stage}-${e.timestamp}`;
      if (seenRef.current.has(key)) return false;
      seenRef.current.add(key);
      return true;
    });

    if (newEvents.length === 0) return;

    const items = newEvents.map((e) => ({
      id: Math.random().toString(36).slice(2),
      icon: eventIcon(e.type),
      stage: stageLabel(e.stage || e.status),
      message: e.message || e.detail || "",
      exiting: false,
    }));

    setToasts((prev) => [...prev, ...items]);

    // Schedule per-toast auto-dismiss timers immediately
    items.forEach((toast) => {
      const exitTimer = setTimeout(() => {
        setToasts((prev) =>
          prev.map((x) => (x.id === toast.id ? { ...x, exiting: true } : x))
        );
      }, DISPLAY_MS);

      const removeTimer = setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.id !== toast.id));
        delete timersRef.current[toast.id];
      }, DISPLAY_MS + EXIT_MS);

      timersRef.current[toast.id] = [exitTimer, removeTimer];
    });
  }, [events]);

  // Clean up all pending timers on unmount
  useEffect(() => {
    return () => {
      Object.values(timersRef.current).flat().forEach(clearTimeout);
    };
  }, []);

  if (toasts.length === 0) return null;

  return createPortal(
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {toasts.map((t) => (
        <div key={t.id} className={`toast${t.exiting ? " toast-exiting" : ""}`} role="status">
          <span className="toast-icon">{t.icon}</span>
          <div className="toast-body">
            {t.stage && <div className="toast-stage">{t.stage}</div>}
            {t.message && <div className="toast-message">{t.message}</div>}
          </div>
        </div>
      ))}
    </div>,
    document.body
  );
}
