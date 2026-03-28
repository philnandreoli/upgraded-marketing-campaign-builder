import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getWorkspace,
  listPersonas,
  createPersona,
  updatePersona,
  deletePersona,
} from "../api";
import { useUser } from "../UserContext";
import { useConfirm } from "../ConfirmDialogContext";
import { SkeletonCard } from "../components/Skeleton";
import PersonaForm from "../components/PersonaForm";

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function PersonaLibrary() {
  const { id: workspaceId } = useParams();
  const { isAdmin } = useUser();
  const confirm = useConfirm();

  const [workspace, setWorkspace] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingPersonas, setLoadingPersonas] = useState(true);
  const [error, setError] = useState(null);

  // Modal state
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null); // persona being edited
  const [formLoading, setFormLoading] = useState(false);
  const [formError, setFormError] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");

  // Fetch workspace
  useEffect(() => {
    setLoadingWs(true);
    getWorkspace(workspaceId)
      .then(setWorkspace)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingWs(false));
  }, [workspaceId]);

  // Fetch personas
  const loadPersonas = useCallback(async () => {
    try {
      const res = await listPersonas(workspaceId);
      setPersonas(res.items ?? []);
    } catch {
      /* silent */
    } finally {
      setLoadingPersonas(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setLoadingPersonas(true);
    loadPersonas();
  }, [loadPersonas]);

  const canWrite = isAdmin || (workspace?.role === "creator");

  // Create / Edit handlers
  const handleOpenCreate = () => {
    setEditTarget(null);
    setFormError(null);
    setFormOpen(true);
  };

  const handleOpenEdit = (persona) => {
    setEditTarget(persona);
    setFormError(null);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditTarget(null);
    setFormError(null);
  };

  const handleFormSubmit = async ({ name, description }) => {
    setFormLoading(true);
    setFormError(null);
    try {
      if (editTarget) {
        const updated = await updatePersona(workspaceId, editTarget.id, { name, description });
        setPersonas((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      } else {
        const created = await createPersona(workspaceId, { name, description });
        setPersonas((prev) => [created, ...prev]);
      }
      handleFormClose();
    } catch (err) {
      setFormError(err.message || "Failed to save persona.");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (persona) => {
    const confirmed = await confirm({
      title: "Delete this persona?",
      message: `"${persona.name}" will be permanently deleted.`,
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await deletePersona(workspaceId, persona.id);
      setPersonas((prev) => prev.filter((p) => p.id !== persona.id));
    } catch {
      setError("Failed to delete persona.");
    }
  };

  // Search
  const filtered = searchQuery.trim()
    ? personas.filter(
        (p) =>
          p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          p.description.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : personas;

  // Loading / error states
  if (loadingWs) {
    return (
      <div>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <p style={{ color: "var(--color-danger)" }}>Error: {error}</p>
        <Link to={`/workspaces/${workspaceId}`} className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          ← Back to Workspace
        </Link>
      </div>
    );
  }

  if (!workspace) return null;

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="breadcrumb">
        <Link to="/">Dashboard</Link>
        <span className="breadcrumb-divider">/</span>
        <Link to="/workspaces">Workspaces</Link>
        <span className="breadcrumb-divider">/</span>
        <Link to={`/workspaces/${workspaceId}`}>{workspace.name}</Link>
        <span className="breadcrumb-divider">/</span>
        <span>Personas</span>
      </nav>

      {/* Header */}
      <div className="section-header">
        <h2>👤 Persona Library</h2>
        {canWrite && (
          <button className="btn btn-primary" onClick={handleOpenCreate}>
            + New Persona
          </button>
        )}
      </div>

      {/* Search */}
      {personas.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <input
            type="search"
            placeholder="Search personas…"
            aria-label="Search personas"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: "100%", maxWidth: "24rem" }}
          />
        </div>
      )}

      {/* Persona list */}
      {loadingPersonas && personas.length === 0 ? (
        <div>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : personas.length === 0 ? (
        <div className="workspace-empty-state card">
          <p>No personas in this workspace yet.</p>
          {canWrite && (
            <button className="btn btn-primary" style={{ marginTop: "0.75rem" }} onClick={handleOpenCreate}>
              Create your first persona
            </button>
          )}
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h2 className="empty-state-title">No personas match your search</h2>
          <p className="empty-state-body">
            No results for &ldquo;{searchQuery}&rdquo;.{" "}
            <button className="empty-state-reset" onClick={() => setSearchQuery("")}>
              Clear search
            </button>
          </p>
        </div>
      ) : (
        <div className="campaign-list">
          {filtered.map((persona) => (
            <div key={persona.id} className="campaign-card card" data-testid={`persona-card-${persona.id}`}>
              <div className="campaign-card-avatar">👤</div>
              <div className="campaign-card-body">
                <span className="campaign-card-title">{persona.name}</span>
                <p className="campaign-card-goal">{persona.description}</p>
                <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                  Created {formatDate(persona.created_at)}
                </span>
              </div>
              {canWrite && (
                <div className="campaign-card-meta">
                  <button
                    className="btn btn-outline"
                    style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                    onClick={() => handleOpenEdit(persona)}
                  >
                    Edit
                  </button>
                  <button
                    className="btn btn-outline"
                    style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                    onClick={() => handleDelete(persona)}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit modal */}
      <PersonaForm
        open={formOpen}
        onClose={handleFormClose}
        onSubmit={handleFormSubmit}
        initial={editTarget ? { name: editTarget.name, description: editTarget.description } : {}}
        loading={formLoading}
        title={editTarget ? "Edit Persona" : "Create Persona"}
        error={formError}
      />
    </div>
  );
}
