import { useState } from "react";

export const SAVED_VIEWS_STORAGE_KEY = "dashboard-saved-views";
export const MAX_SAVED_VIEWS = 10;

/**
 * Read saved views from localStorage, returning an empty array on parse errors.
 */
function readViews() {
  try {
    const raw = localStorage.getItem(SAVED_VIEWS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * useSavedViews — manages user-created saved filter views in localStorage.
 *
 * Returns:
 *   views      array   — current list of saved views
 *   addView    fn      — (name, filter, search) → true on success, false when at limit
 *   removeView fn      — (id) removes the view with that id
 *   renameView fn      — (id, name) renames the view with that id
 */
export default function useSavedViews() {
  const [views, setViews] = useState(readViews);

  const persist = (next) => {
    setViews(next);
    localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, JSON.stringify(next));
  };

  const addView = (name, filter, search) => {
    if (views.length >= MAX_SAVED_VIEWS) return false;
    const newView = {
      id: crypto.randomUUID(),
      name: name.trim(),
      filter,
      search,
    };
    persist([...views, newView]);
    return true;
  };

  const removeView = (id) => {
    persist(views.filter((v) => v.id !== id));
  };

  const renameView = (id, name) => {
    persist(views.map((v) => (v.id === id ? { ...v, name: name.trim() } : v)));
  };

  return { views, addView, removeView, renameView };
}
