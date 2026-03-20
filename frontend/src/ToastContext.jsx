import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const ToastContext = createContext(null);

const DISPLAY_MS = 5000;
const EXIT_MS = 200;

/**
 * ToastProvider — provides a global addToast() function via context.
 * Renders its own portal for programmatic toast notifications (e.g. error alerts).
 *
 * Coexists with the existing Toast component used for WebSocket events.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef({});

  const addToast = useCallback(({ icon = "❌", stage, message, duration = DISPLAY_MS } = {}) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, icon, stage, message, exiting: false }]);

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
  }, []);

  // Clean up timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).flat().forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      {toasts.length > 0 &&
        createPortal(
          <div className="toast-container toast-container--context" aria-live="polite" aria-atomic="false">
            {toasts.map((t) => (
              <div key={t.id} className={`toast toast--error${t.exiting ? " toast-exiting" : ""}`} role="status">
                <span className="toast-icon">{t.icon}</span>
                <div className="toast-body">
                  {t.stage && <div className="toast-stage">{t.stage}</div>}
                  {t.message && <div className="toast-message">{t.message}</div>}
                </div>
              </div>
            ))}
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

/**
 * useToast — returns an addToast() function to show themed notifications.
 *
 * Usage:
 *   const addToast = useToast();
 *   addToast({ stage: "Error", message: "Something went wrong" });
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
