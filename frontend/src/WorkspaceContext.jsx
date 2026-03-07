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

  const fetchWorkspaces = useCallback(() => {
    setLoading(true);
    listWorkspaces()
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  const personalWorkspace = workspaces.find((ws) => ws.is_personal) ?? null;

  const value = {
    workspaces,
    loading,
    refreshWorkspaces: fetchWorkspaces,
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
