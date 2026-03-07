import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createWorkspace } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";

const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

function WorkspaceCard({ ws }) {
  const descriptionPreview = ws.description
    ? ws.description.length > 100
      ? ws.description.slice(0, 100) + "…"
      : ws.description
    : null;

  return (
    <Link to={`/workspaces/${ws.id}`} className="ws-card card" aria-label={`Open workspace ${ws.name}`}>
      <div className="ws-card-header">
        <span className="ws-card-icon">{ws.is_personal ? "🏠" : "📁"}</span>
        <span className="ws-card-name">{ws.name}</span>
        {ws.is_personal && (
          <span className="ws-card-personal-badge">Personal</span>
        )}
        {ws.role && (
          <span className={`workspace-role-badge workspace-role-badge--${ws.role}`}>
            {ROLE_LABELS[ws.role] ?? ws.role}
          </span>
        )}
      </div>
      {descriptionPreview && (
        <p className="ws-card-description">{descriptionPreview}</p>
      )}
      <div className="ws-card-stats">
        <span className="ws-card-stat">
          <span className="ws-card-stat-value">{ws.member_count ?? "—"}</span>
          <span className="ws-card-stat-label">Members</span>
        </span>
        <span className="ws-card-stat">
          <span className="ws-card-stat-value">{ws.campaign_count ?? "—"}</span>
          <span className="ws-card-stat-label">Campaigns</span>
        </span>
      </div>
    </Link>
  );
}

function CreateWorkspaceModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const ws = await createWorkspace(name.trim(), description.trim() || undefined);
      onCreated(ws);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="create-ws-title">
      <div className="modal-box card">
        <div className="modal-header">
          <h2 id="create-ws-title">Create Workspace</h2>
          <button className="modal-close btn btn-outline" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="ws-name">Name <span aria-hidden="true">*</span></label>
            <input
              id="ws-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My team workspace"
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="ws-description">Description</label>
            <textarea
              id="ws-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description…"
            />
          </div>
          {error && (
            <p style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
              {error}
            </p>
          )}
          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-outline" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
              {saving ? "Creating…" : "Create Workspace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function WorkspaceList() {
  const { workspaces, loading, refreshWorkspaces } = useWorkspace();
  const { isViewer } = useUser();
  const navigate = useNavigate();
  const [showCreate, setShowCreate] = useState(false);

  const sortedWorkspaces = [...workspaces].sort((a, b) => {
    if (a.is_personal && !b.is_personal) return -1;
    if (!a.is_personal && b.is_personal) return 1;
    return a.name.localeCompare(b.name);
  });

  const handleCreated = async (ws) => {
    setShowCreate(false);
    refreshWorkspaces();
    navigate(`/workspaces/${ws.id}`);
  };

  return (
    <div>
      <div className="section-header">
        <h2>Workspaces</h2>
        {!isViewer && (
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            + Create Workspace
          </button>
        )}
      </div>

      {loading ? (
        <div className="loading">
          <span className="spinner" /> Loading workspaces…
        </div>
      ) : workspaces.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📁</div>
          <h2 className="empty-state-title">No workspaces yet</h2>
          <p className="empty-state-body">Create a workspace to organise your campaigns.</p>
          {!isViewer && (
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
              + Create your first workspace
            </button>
          )}
        </div>
      ) : (
        <div className="ws-card-grid">
          {sortedWorkspaces.map((ws) => (
            <WorkspaceCard key={ws.id} ws={ws} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateWorkspaceModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}
