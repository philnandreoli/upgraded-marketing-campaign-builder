import { useThemeContext } from "../ThemeContext.jsx";

/**
 * Thin wrapper around ThemeContext for backward-compatible usage.
 * Returns { theme, toggleTheme } — the resolved effective theme and a
 * toggle that cycles between "dark" and "light" (persisted to backend).
 */
export default function useTheme() {
  const { theme, setTheme } = useThemeContext();

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return { theme, toggleTheme };
}
