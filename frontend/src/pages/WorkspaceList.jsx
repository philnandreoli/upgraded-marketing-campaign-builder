import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createWorkspace } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";

const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

/* ── Inline style constants ──────────────────────────────────────────── */

const summaryStripStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.75rem",
  padding: "0.875rem 1rem",
  marginBottom: "1.25rem",
  borderRadius: "var(--radius, 8px)",
  background: "var(--color-surface, #f8fafc)",
  border: "1px solid var(--color-border, #e2e8f0)",
};

const summaryItemStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.375rem",
  fontSize: "0.875rem",
  color: "var(--color-text-secondary, #64748b)",
};

const summaryValueStyle = {
  fontWeight: 700,
  color: "var(--color-text, #1e293b)",
  fontSize: "1rem",
};

const summaryWarningValueStyle = {
  ...summaryValueStyle,
  color: "var(--color-warning, #d97706)",
};

const statusBreakdownStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.375rem",
  marginTop: "0.5rem",
  paddingTop: "0.5rem",
  borderTop: "1px solid var(--color-border, #e2e8f0)",
};

const statusBadgeBase = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.25rem",
  fontSize: "0.75rem",
  padding: "0.125rem 0.5rem",
  borderRadius: "999px",
  fontWeight: 500,
  lineHeight: 1.4,
};

const statusBadgeStyles = {
  draft: { ...statusBadgeBase, background: "var(--color-badge-draft-bg, #f1f5f9)", color: "var(--color-badge-draft-fg, #475569)" },
  in_progress: { ...statusBadgeBase, background: "var(--color-badge-progress-bg, #dbeafe)", color: "var(--color-badge-progress-fg, #1d4ed8)" },
  awaiting_approval: { ...statusBadgeBase, background: "var(--color-badge-warning-bg, #fef3c7)", color: "var(--color-badge-warning-fg, #92400e)", fontWeight: 700 },
  approved: { ...statusBadgeBase, background: "var(--color-badge-success-bg, #d1fae5)", color: "var(--color-badge-success-fg, #065f46)" },
};

const actionBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.25rem",
  fontSize: "0.75rem",
  fontWeight: 700,
  padding: "0.1875rem 0.5rem",
  borderRadius: "999px",
  background: "var(--color-warning, #d97706)",
  color: "#fff",
  marginLeft: "auto",
};

/* ── Helpers ─────────────────────────────────────────────────────────── */

function plural(count, singular, pluralForm) {
  return count === 1 ? `${count} ${singular}` : `${count} ${pluralForm ?? singular + "s"}`;
}

function formatMoney(value, { showSign = false } = {}) {
  const amount = Number(value ?? 0);
  const normalized = Number.isFinite(amount) ? amount : 0;
  return normalized.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: showSign ? "always" : "auto",
  });
}

/* ── SummaryStrip ────────────────────────────────────────────────────── */

function SummaryStrip({ workspaces }) {
  const totals = useMemo(() => {
    let campaigns = 0, drafts = 0, inProgress = 0, awaiting = 0, approved = 0;
    for (const ws of workspaces) {
      campaigns += ws.campaign_count ?? 0;
      drafts += ws.draft_count ?? 0;
      inProgress += ws.in_progress_count ?? 0;
      awaiting += ws.awaiting_approval_count ?? 0;
      approved += ws.approved_count ?? 0;
    }
    return { campaigns, drafts, inProgress, awaiting, approved };
  }, [workspaces]);

  return (
    <div className="ws-summary-strip" style={summaryStripStyle} role="region" aria-label="Cross-workspace summary">
      <span style={summaryItemStyle}>
        <span style={summaryValueStyle} data-testid="summary-campaigns">{totals.campaigns}</span> Campaigns
      </span>
      <span style={summaryItemStyle}>
        <span style={summaryValueStyle} data-testid="summary-drafts">{totals.drafts}</span> Drafts
      </span>
      <span style={summaryItemStyle}>
        <span style={summaryValueStyle} data-testid="summary-in-progress">{totals.inProgress}</span> In Progress
      </span>
      <span style={summaryItemStyle}>
        <span style={totals.awaiting > 0 ? summaryWarningValueStyle : summaryValueStyle} data-testid="summary-awaiting">{totals.awaiting}</span> Awaiting Approval
      </span>
      <span style={summaryItemStyle}>
        <span style={summaryValueStyle} data-testid="summary-approved">{totals.approved}</span> Approved
      </span>
    </div>
  );
}

/* ── WorkspaceCard ───────────────────────────────────────────────────── */

function WorkspaceCard({ ws }) {
  const descriptionPreview = ws.description
    ? ws.description.length > 100
      ? ws.description.slice(0, 100) + "…"
      : ws.description
    : null;

  const hasStatusBreakdown =
    (ws.draft_count ?? 0) > 0 ||
    (ws.in_progress_count ?? 0) > 0 ||
    (ws.awaiting_approval_count ?? 0) > 0 ||
    (ws.approved_count ?? 0) > 0;

  const budgetTotal = Number(ws.budget_total ?? 0);
  const actualTotal = Number(ws.actual_total ?? 0);
  const varianceTotal = Number(ws.variance_total ?? 0);
  const hasBudgetInfo = budgetTotal !== 0 || actualTotal !== 0 || varianceTotal !== 0;
  const actualBudgetToneClass =
    budgetTotal > 0
      ? (actualTotal > budgetTotal ? "ws-finance-value--actual-over" : "ws-finance-value--actual-good")
      : "ws-finance-value--actual-neutral";
  const varianceToneClass =
    varianceTotal > 0
      ? "ws-finance-value--variance-over"
      : varianceTotal < 0
        ? "ws-finance-value--variance-good"
        : "ws-finance-value--variance-neutral";

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
        {(ws.awaiting_approval_count ?? 0) > 0 && (
          <span className="ws-action-badge" style={actionBadgeStyle} aria-label="Awaiting your action">
            ⚠ Needs Action
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
      {hasBudgetInfo && (
        <div className="ws-card-stats ws-card-finance-stats">
          <span className="ws-card-stat">
            <span className="ws-card-stat-value ws-finance-value--budget">{formatMoney(budgetTotal)}</span>
            <span className="ws-card-stat-label">Budget</span>
          </span>
          <span className="ws-card-stat">
            <span className={`ws-card-stat-value ${actualBudgetToneClass}`}>{formatMoney(actualTotal)}</span>
            <span className="ws-card-stat-label">Actual</span>
          </span>
          <span className="ws-card-stat">
            <span className={`ws-card-stat-value ${varianceToneClass}`}>{formatMoney(varianceTotal, { showSign: true })}</span>
            <span className="ws-card-stat-label">Variance</span>
          </span>
        </div>
      )}
      {hasStatusBreakdown && (
        <div className="ws-card-status-breakdown" style={statusBreakdownStyle}>
          {(ws.draft_count ?? 0) > 0 && (
            <span className="ws-status-badge ws-status-badge--draft" style={statusBadgeStyles.draft}>
              {plural(ws.draft_count, "Draft")}
            </span>
          )}
          {(ws.in_progress_count ?? 0) > 0 && (
            <span className="ws-status-badge ws-status-badge--in-progress" style={statusBadgeStyles.in_progress}>
              {plural(ws.in_progress_count, "In Progress", "In Progress")}
            </span>
          )}
          {(ws.awaiting_approval_count ?? 0) > 0 && (
            <span className="ws-status-badge ws-status-badge--awaiting" style={statusBadgeStyles.awaiting_approval}>
              {plural(ws.awaiting_approval_count, "Awaiting Approval", "Awaiting Approval")}
            </span>
          )}
          {(ws.approved_count ?? 0) > 0 && (
            <span className="ws-status-badge ws-status-badge--approved" style={statusBadgeStyles.approved}>
              {plural(ws.approved_count, "Approved", "Approved")}
            </span>
          )}
        </div>
      )}
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
        <>
          <SummaryStrip workspaces={workspaces} />
          <div className="ws-card-grid">
            {sortedWorkspaces.map((ws) => (
              <WorkspaceCard key={ws.id} ws={ws} />
            ))}
          </div>
        </>
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
