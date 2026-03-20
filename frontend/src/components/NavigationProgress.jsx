import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

/**
 * NavigationProgress — thin top-of-page progress bar that animates on
 * route changes, giving users instant visual feedback during navigation.
 *
 * Uses `useLocation()` to detect route transitions.  On each change the
 * bar rapidly fills to ~80 %, then completes to 100 % and fades out.
 * Fast back-to-back navigations reset the bar without a visible flash.
 *
 * DOM class names are toggled via a ref so that the effect never calls
 * setState synchronously, keeping the React render loop efficient.
 */
export default function NavigationProgress() {
  const location = useLocation();
  const barRef = useRef(null);
  const prevKey = useRef(location.key);
  const timeouts = useRef([]);

  useEffect(() => {
    // Skip the initial mount — only animate on actual navigation.
    if (prevKey.current === location.key) return;
    prevKey.current = location.key;

    const el = barRef.current;
    if (!el) return;

    // Clear any pending timers from a previous navigation.
    timeouts.current.forEach(clearTimeout);
    timeouts.current = [];

    // 1. Start growing → rapidly fills to ~80 %
    el.className = "nav-progress nav-progress--growing";

    // 2. After the route component mounts, complete to 100 %
    const t1 = setTimeout(() => {
      el.className = "nav-progress nav-progress--complete";
    }, 150);

    // 3. Fade out
    const t2 = setTimeout(() => {
      el.className = "nav-progress nav-progress--fadeout";
    }, 450);

    // 4. Reset to hidden (base class only — no width, invisible)
    const t3 = setTimeout(() => {
      el.className = "nav-progress";
    }, 750);

    timeouts.current = [t1, t2, t3];

    return () => {
      timeouts.current.forEach(clearTimeout);
      timeouts.current = [];
    };
  }, [location]);

  return (
    <div
      ref={barRef}
      className="nav-progress"
      role="progressbar"
      aria-label="Page loading"
    />
  );
}
