import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { listWorkspaces } from "./api";
import { useUser } from "./UserContext";

const WorkspaceContext = createContext(null);

const DEFAULT_VALUE = {
  workspaces: [],
  loading: true,
  refreshWorkspaces: () => {},
  personalWorkspace: null,
};

const authEnabled = !!import.meta.env.VITE_AZURE_CLIENT_ID;

export function WorkspaceProvider({ children }) {
  const userCtx = useUser();
  const userId = userCtx?.user?.id ?? null;
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [didRetryEmpty, setDidRetryEmpty] = useState(false);
  const lastRefreshedUserIdRef = useRef(null);

  // Internal fetch — does NOT call setLoading(true) synchronously so it is
  // safe to call from within a useEffect without triggering the
  // react-hooks/set-state-in-effect lint rule. loading starts as true and is
  // only ever set to false (async) once the request resolves.
  const doFetch = useCallback(() => {
    listWorkspaces()
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    doFetch();
  }, [doFetch]);

  // In authenticated mode, first-load races can briefly return an empty list
  // before JIT user provisioning commits. Retry once to recover automatically.
  useEffect(() => {
    if (!authEnabled || loading || didRetryEmpty || workspaces.length > 0) return;
    const timerId = setTimeout(() => {
      setDidRetryEmpty(true);
      setLoading(true);
      doFetch();
    }, 0);
    return () => clearTimeout(timerId);
  }, [loading, workspaces.length, didRetryEmpty, doFetch]);

  useEffect(() => {
    if (!authEnabled || !userId || loading || lastRefreshedUserIdRef.current === userId) return;
    if (workspaces.length > 0) {
      lastRefreshedUserIdRef.current = userId;
      return;
    }
    const timerId = setTimeout(() => {
      lastRefreshedUserIdRef.current = userId;
      setLoading(true);
      doFetch();
    }, 0);
    return () => clearTimeout(timerId);
  }, [userId, loading, workspaces.length, doFetch]);

  // Public API — sets loading=true before re-fetching. Safe to call from
  // event handlers / mutation callbacks (not from within effects).
  const refreshWorkspaces = useCallback(() => {
    setDidRetryEmpty(false);
    setLoading(true);
    doFetch();
  }, [doFetch]);

  const personalWorkspace = workspaces.find((ws) => ws.is_personal) ?? null;

  const value = {
    workspaces,
    loading,
    refreshWorkspaces,
    personalWorkspace,
  };

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  return ctx ?? DEFAULT_VALUE;
}
