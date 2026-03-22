import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const ToastContext = createContext(null);

const DISPLAY_MS = 5000;
const EXIT_MS = 200;

/**
 * Derives the type icon for a given toast type.
 */
function typeIcon(type) {
  switch (type) {
    case "success": return "✓";
    case "warning": return "⚠️";
    case "error":   return "✕";
    case "info":
    default:        return "ℹ";
  }
}

/**
 * ToastProvider — provides addToast() and dismissToast() functions via context.
 * Renders its own portal for programmatic toast notifications.
 *
 * Supports toast types (success/warning/error/info) with corresponding icons
 * and left-border color accents, an optional action button (e.g. Undo), and
 * a dismiss (✕) button on every toast.
 *
 * Coexists with the existing Toast component used for WebSocket events.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef({});

  const dismissToast = useCallback((id) => {
    // Clear pending auto-dismiss timers
    (timersRef.current[id] || []).forEach(clearTimeout);
    delete timersRef.current[id];
    // Trigger exit animation, then remove
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)));
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), EXIT_MS);
  }, []);

  const addToast = useCallback(({ type = "info", icon, stage, message, duration = DISPLAY_MS, action } = {}) => {
    const id = Math.random().toString(36).slice(2);
    const resolvedIcon = icon ?? typeIcon(type);
    setToasts((prev) => [...prev, { id, type, icon: resolvedIcon, stage, message, action, exiting: false }]);

    const exitTimer = setTimeout(() => {
      setToasts((prev) =>
        prev.map((t) => (t.id === id ? { ...t, exiting: true } : t))
      );
    }, duration);

    const removeTimer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      delete timersRef.current[id];
    }, duration + EXIT_MS);

    timersRef.current[id] = [exitTimer, removeTimer];
    return id;
  }, []);

  // Clean up timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).flat().forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ addToast, dismissToast }}>
      {children}
      {toasts.length > 0 &&
        createPortal(
          <div className="toast-container toast-container--context" aria-live="polite" aria-atomic="false">
            {toasts.map((t) => (
              <div key={t.id} className={`toast${t.type ? ` toast--${t.type}` : ""}${t.exiting ? " toast-exiting" : ""}`} role="status">
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
                  onClick={() => dismissToast(t.id)}
                  aria-label="Dismiss notification"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

/**
 * useToast — returns { addToast, dismissToast } for showing themed notifications.
 *
 * Usage:
 *   const { addToast, dismissToast } = useToast();
 *   const id = addToast({ type: "success", stage: "Saved", message: "Settings saved" });
 *   dismissToast(id);  // optional manual dismiss
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
