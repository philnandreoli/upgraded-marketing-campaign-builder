import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getWorkspace,
  listPersonas,
  createPersona,
  updatePersona,
  deletePersona,
  parsePersona,
} from "../api";
import { useUser } from "../UserContext";
import { useConfirm } from "../ConfirmDialogContext";
import { SkeletonCard } from "../components/Skeleton";
import PersonaForm from "../components/PersonaForm";
import PersonaEditor, { parseDescriptionToFields } from "../components/PersonaEditor";

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

  // Modal state — phase 1: freeform describe, phase 2: structured editor
  const [phase, setPhase] = useState(null); // null | 'freeform' | 'editor'
  const [editTarget, setEditTarget] = useState(null); // persona being edited
  const [freeformInput, setFreeformInput] = useState({ name: "", description: "" });
  const [parsedFields, setParsedFields] = useState(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [parseError, setParseError] = useState(null);
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
    setFreeformInput({ name: "", description: "" });
    setParsedFields(null);
    setParseError(null);
    setFormError(null);
    setPhase("freeform");
  };

  const handleOpenEdit = (persona) => {
    setEditTarget(persona);
    setParsedFields(parseDescriptionToFields(persona.description));
    setFormError(null);
    setPhase("editor");
  };

  const handleCloseAll = () => {
    setPhase(null);
    setEditTarget(null);
    setParsedFields(null);
    setParseError(null);
    setFormError(null);
    setFreeformInput({ name: "", description: "" });
  };

  // "✨ Structure with AI" — call parse endpoint, transition to editor
  const handleStructureWithAI = async ({ name, description }) => {
    setParseLoading(true);
    setParseError(null);
    try {
      const result = await parsePersona(workspaceId, { name, description });
      setParsedFields(result);
      setPhase("editor");
    } catch (err) {
      // Log for developer visibility; user sees a friendly message
      console.warn("AI persona parse failed:", err);
      setParseError("AI structuring failed. You can fill the fields manually.");
      setParsedFields({ name, demographics: description, psychographics: "", pain_points: "", behaviors: "", channels: "" });
      setPhase("editor");
    } finally {
      setParseLoading(false);
    }
  };

  // Skip AI — open PersonaEditor directly for manual creation
  const handleSkipAI = ({ name, description }) => {
    setParsedFields({ name, demographics: description, psychographics: "", pain_points: "", behaviors: "", channels: "" });
    setParseError(null);
    setPhase("editor");
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
      handleCloseAll();
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

      {/* Phase 1: Freeform describe modal */}
      <PersonaForm
        open={phase === "freeform"}
        onClose={handleCloseAll}
        onSubmit={handleStructureWithAI}
        onSkip={handleSkipAI}
        initial={freeformInput}
        loading={parseLoading}
        title="Describe Your Persona"
        error={parseError}
        submitLabel="✨ Structure with AI"
      />

      {/* Phase 2: Structured editor modal (create or edit) */}
      <PersonaEditor
        open={phase === "editor"}
        onClose={handleCloseAll}
        onBack={editTarget ? undefined : () => setPhase("freeform")}
        onSubmit={handleFormSubmit}
        initial={editTarget
          ? { name: editTarget.name, ...parseDescriptionToFields(editTarget.description) }
          : (parsedFields ?? {})
        }
        loading={formLoading}
        title={editTarget ? "Edit Persona" : "Review & Save Persona"}
        error={formError}
      />
    </div>
  );
}
