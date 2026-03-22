import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { getMeSettings, patchMeSettings } from "./api";

const ThemeContext = createContext(null);

const STORAGE_KEY = "theme";

/**
 * Resolve a preference string ("light" | "dark" | "system") to an effective
 * theme ("light" | "dark") by checking the OS preference when needed.
 */
function resolveTheme(preference) {
  if (preference === "light" || preference === "dark") return preference;
  // "system" or unknown — defer to OS, default dark
  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) return "light";
  return "dark";
}

/** Read the initial preference from localStorage (before backend is available). */
function getLocalPreference() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return null;
}

/**
 * ThemeProvider — single source of truth for theme across the app.
 *
 * On mount it applies the localStorage / OS preference immediately (no flash),
 * then fetches the user's backend preference and reconciles.
 *
 * Exposes:
 *   preference  — raw stored value ("light" | "dark" | "system")
 *   theme       — resolved effective theme ("light" | "dark")
 *   setTheme(p) — update preference everywhere (context + localStorage + DOM + backend)
 */
export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(() => getLocalPreference() ?? "system");
  const [theme, setEffective] = useState(() => resolveTheme(getLocalPreference() ?? "system"));
  const backendFetched = useRef(false);

  // ── Apply preference to DOM + localStorage whenever it changes ──────────
  useEffect(() => {
    const effective = resolveTheme(preference);
    setEffective(effective);
    document.documentElement.setAttribute("data-theme", effective);
    localStorage.setItem(STORAGE_KEY, preference);
  }, [preference]);

  // ── Listen for OS-level changes when preference is "system" ─────────────
  useEffect(() => {
    if (preference !== "system") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const handler = () => {
      const eff = resolveTheme("system");
      setEffective(eff);
      document.documentElement.setAttribute("data-theme", eff);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [preference]);

  // ── Fetch backend preference on mount ───────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    getMeSettings()
      .then((settings) => {
        if (cancelled) return;
        backendFetched.current = true;
        const backendTheme = settings?.theme;
        if (backendTheme === "light" || backendTheme === "dark" || backendTheme === "system") {
          setPreference(backendTheme);
        }
      })
      .catch(() => {
        // Backend unreachable — keep localStorage / OS fallback (already applied)
      });
    return () => { cancelled = true; };
  }, []);

  // ── Public setter: update preference + optionally persist to backend ──
  const setTheme = useCallback((newPref, { persist = true } = {}) => {
    const pref = newPref === "light" || newPref === "dark" || newPref === "system" ? newPref : "system";
    setPreference(pref);
    if (persist) {
      // Fire-and-forget persist to backend
      patchMeSettings({ theme: pref }).catch(() => {
        // Silently ignore — localStorage is already updated so the choice
        // is preserved locally even if the network call fails.
      });
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, preference, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useThemeContext() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useThemeContext must be used within ThemeProvider");
  return ctx;
}
