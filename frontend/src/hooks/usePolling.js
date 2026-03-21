import { useEffect, useRef } from "react";

/**
 * Reusable polling hook that respects tab visibility.
 *
 * – Calls `callback` on the given `interval` while the tab is visible.
 * – Pauses the interval when the tab becomes hidden.
 * – Fires an immediate `callback` when the tab becomes visible again,
 *   then resumes the regular interval.
 *
 * The hook does **not** invoke `callback` on mount — the consumer is
 * expected to handle the initial fetch separately.
 *
 * @param {() => void} callback  Function to call each tick.
 * @param {number|null} interval Milliseconds between ticks (when visible).
 *                               Pass `null` to disable polling entirely.
 */
export default function usePolling(callback, interval) {
  const callbackRef = useRef(callback);
  const timerRef = useRef(null);

  // Keep the ref up-to-date so the interval always calls the latest callback
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    // Disabled when interval is null / undefined / 0
    if (!interval) return;

    function start() {
      // Avoid duplicate timers
      stop();
      timerRef.current = setInterval(() => callbackRef.current(), interval);
    }

    function stop() {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        // Immediate fetch on re-focus, then resume interval
        callbackRef.current();
        start();
      } else {
        stop();
      }
    }

    // Start polling only if the page is currently visible
    if (document.visibilityState === "visible") {
      start();
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [interval]);
}
