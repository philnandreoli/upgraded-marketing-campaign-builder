import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { listWorkspaces } from "./api";

const WorkspaceContext = createContext(null);

const DEFAULT_VALUE = {
  workspaces: [],
  loading: true,
  refreshWorkspaces: () => {},
  personalWorkspace: null,
};

export function WorkspaceProvider({ children }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);

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

  // Public API — sets loading=true before re-fetching. Safe to call from
  // event handlers / mutation callbacks (not from within effects).
  const refreshWorkspaces = useCallback(() => {
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
