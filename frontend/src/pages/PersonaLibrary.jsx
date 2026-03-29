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
import SearchBar from "../components/SearchBar";
import PersonaForm from "../components/PersonaForm";
import PersonaEditor from "../components/PersonaEditor";
import { parseDescriptionToFields } from "../utils/personaUtils";

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
    setFreeformInput({ name, description });
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
    setFreeformInput({ name, description });
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
        const created = await createPersona(workspaceId, {
          name,
          description,
          source_text: freeformInput.description || "",
        });
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
        <>
          <SearchBar
            value={searchQuery}
            onChange={(value) => setSearchQuery(value)}
            onClear={() => setSearchQuery("")}
            placeholder="Search personas…"
          />
          {searchQuery && (
            <span className="search-result-count">
              Showing {filtered.length} of {personas.length} persona{personas.length !== 1 ? "s" : ""}
            </span>
          )}
        </>
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
        <div className="persona-grid">
          {filtered.map((persona) => {
            const fields = parseDescriptionToFields(persona.description);
            const initials = persona.name
              .split(/\s+/)
              .map((w) => w[0])
              .slice(0, 2)
              .join("");
            return (
              <div key={persona.id} className="persona-card card" data-testid={`persona-card-${persona.id}`}>
                <div className="persona-card__header">
                  <div className="persona-card__avatar">{initials}</div>
                  <span className="persona-card__name">{persona.name}</span>
                </div>
                <div className="persona-card__body">
                  {fields.demographics && (
                    <div className="persona-card__field">
                      <span className="persona-card__field-label">Demographics</span>
                      {fields.demographics}
                    </div>
                  )}
                  {fields.psychographics && (
                    <div className="persona-card__field">
                      <span className="persona-card__field-label">Psychographics</span>
                      {fields.psychographics}
                    </div>
                  )}
                  {fields.pain_points && (
                    <div className="persona-card__field">
                      <span className="persona-card__field-label">Pain Points</span>
                      {fields.pain_points}
                    </div>
                  )}
                  {fields.behaviors && (
                    <div className="persona-card__field">
                      <span className="persona-card__field-label">Behaviors</span>
                      {fields.behaviors}
                    </div>
                  )}
                  {fields.channels && (
                    <div className="persona-card__field">
                      <span className="persona-card__field-label">Channels</span>
                      {fields.channels}
                    </div>
                  )}
                  {!fields.demographics && !fields.psychographics && !fields.pain_points && !fields.behaviors && !fields.channels && (
                    <div className="persona-card__field">{persona.description}</div>
                  )}
                </div>
                <div className="persona-card__footer">
                  <span className="persona-card__date">Created {formatDate(persona.created_at)}</span>
                  {canWrite && (
                    <div className="persona-card__actions">
                      <button className="btn btn-outline" onClick={() => handleOpenEdit(persona)}>
                        Edit
                      </button>
                      <button className="btn btn-outline" onClick={() => handleDelete(persona)}>
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
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
