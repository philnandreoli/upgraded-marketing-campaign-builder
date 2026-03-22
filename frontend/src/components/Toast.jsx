import { useEffect, useState, useRef, useCallback } from "react";
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
 * Toast — renders auto-dismissing notifications for WebSocket pipeline events,
 * plus optional programmatic notifications (e.g. delete-undo prompts).
 *
 * Hovering a toast pauses its auto-dismiss timer; moving the mouse away resumes it.
 *
 * Props:
 *   events        — array of WebSocket event objects from useWebSocket
 *   notifications — array of manually-managed notification items:
 *                   { id, icon, type, stage, message, action?: { label, onClick } }
 *                   The parent controls adding/removing these; Toast handles
 *                   entry/exit animations when items appear/disappear.
 */
export default function Toast({ events, notifications = [] }) {
  const [toasts, setToasts] = useState([]);
  const [manualToasts, setManualToasts] = useState([]);
  const seenRef = useRef(new Set());
  const timersRef = useRef({});
  const remainingRef = useRef({});
  const prevNotifIdsRef = useRef(new Set());

  /** Schedule exit + remove timers for a toast. */
  const scheduleAutoDismiss = useCallback((toastId, delayMs) => {
    const startedAt = Date.now();
    remainingRef.current[toastId] = { delay: delayMs, startedAt };

    const exitTimer = setTimeout(() => {
      setToasts((prev) =>
        prev.map((x) => (x.id === toastId ? { ...x, exiting: true } : x))
      );
    }, delayMs);

    const removeTimer = setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== toastId));
      delete timersRef.current[toastId];
      delete remainingRef.current[toastId];
    }, delayMs + EXIT_MS);

    timersRef.current[toastId] = { exitTimer, removeTimer, startedAt };
  }, []);

  /** Pause the auto-dismiss timer for a hovered toast. */
  const handleMouseEnter = useCallback((toastId) => {
    const timers = timersRef.current[toastId];
    if (!timers) return;
    clearTimeout(timers.exitTimer);
    clearTimeout(timers.removeTimer);
    const elapsed = Date.now() - timers.startedAt;
    const remaining = Math.max(0, (remainingRef.current[toastId]?.delay ?? DISPLAY_MS) - elapsed);
    remainingRef.current[toastId] = { delay: remaining, startedAt: null };
  }, []);

  /** Resume the auto-dismiss timer when the mouse leaves a toast. */
  const handleMouseLeave = useCallback((toastId) => {
    const info = remainingRef.current[toastId];
    if (!info) return;
    scheduleAutoDismiss(toastId, info.delay);
  }, [scheduleAutoDismiss]);

  /** Dismiss a toast immediately (event toasts or manual notification toasts). */
  const handleDismiss = useCallback((toastId) => {
    // Clear any auto-dismiss timers for event toasts
    const timers = timersRef.current[toastId];
    if (timers) {
      clearTimeout(timers.exitTimer);
      clearTimeout(timers.removeTimer);
      delete timersRef.current[toastId];
      delete remainingRef.current[toastId];
    }
    // Trigger exit animation on event toasts
    setToasts((prev) => prev.map((t) => (t.id === toastId ? { ...t, exiting: true } : t)));
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== toastId)), EXIT_MS);
    // Also handle manual notification toasts
    setManualToasts((prev) => prev.map((t) => (t.id === toastId ? { ...t, exiting: true } : t)));
    setTimeout(() => setManualToasts((prev) => prev.filter((t) => t.id !== toastId)), EXIT_MS);
  }, []);

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
      scheduleAutoDismiss(toast.id, DISPLAY_MS);
    });
  }, [events, scheduleAutoDismiss]);

  // Sync programmatic notifications prop → manualToasts state with animations
  useEffect(() => {
    const currentIds = new Set(notifications.map((n) => n.id));

    // Add newly-appearing notifications
    const newNotifs = notifications.filter((n) => !prevNotifIdsRef.current.has(n.id));
    if (newNotifs.length > 0) {
      setManualToasts((prev) => [
        ...prev,
        ...newNotifs.map((n) => ({ ...n, exiting: false })),
      ]);
    }

    // Trigger exit animation for notifications removed from the prop
    const removedIds = [...prevNotifIdsRef.current].filter((id) => !currentIds.has(id));
    if (removedIds.length > 0) {
      setManualToasts((prev) =>
        prev.map((t) => (removedIds.includes(t.id) ? { ...t, exiting: true } : t))
      );
      setTimeout(() => {
        setManualToasts((prev) => prev.filter((t) => !removedIds.includes(t.id)));
      }, EXIT_MS);
    }

    prevNotifIdsRef.current = currentIds;
  }, [notifications]);

  // Clean up all pending timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach((t) => {
        if (t.exitTimer != null) clearTimeout(t.exitTimer);
        if (t.removeTimer != null) clearTimeout(t.removeTimer);
      });
    };
  }, []);

  const allToasts = [...toasts, ...manualToasts];
  if (allToasts.length === 0) return null;

  return createPortal(
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {allToasts.map((t) => (
        <div
          key={t.id}
          className={`toast${t.type ? ` toast--${t.type}` : ""}${t.exiting ? " toast-exiting" : ""}`}
          role="status"
          onMouseEnter={() => handleMouseEnter(t.id)}
          onMouseLeave={() => handleMouseLeave(t.id)}
        >
          <span className="toast-icon">{t.icon}</span>
          <div className="toast-body">
            {t.stage && <div className="toast-stage">{t.stage}</div>}
            {t.message && <div className="toast-message">{t.message}</div>}
          </div>
          {t.action && (
            <button className="toast-action" onClick={t.action.onClick}>
              {t.action.label}
            </button>
          )}
          <button
            className="toast-dismiss"
            onClick={() => handleDismiss(t.id)}
            aria-label="Dismiss notification"
          >
            ✕
          </button>
        </div>
      ))}
    </div>,
    document.body
  );
}
