import { useState } from "react";
import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge.jsx";

const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

const IN_PROGRESS_STATUSES = [
  "strategy", "content", "channel_planning", "analytics_setup",
  "review", "review_clarification", "content_revision", "clarification",
];
const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];
const APPROVED_STATUSES = ["approved"];

const STATUS_GROUPS = [
  { label: "Drafts", statuses: ["draft"] },
  { label: "In Progress", statuses: IN_PROGRESS_STATUSES },
  { label: "Awaiting Approval", statuses: AWAITING_APPROVAL_STATUSES },
  { label: "Approved", statuses: APPROVED_STATUSES },
];

/**
 * WorkspaceSection — collapsible workspace group for the Dashboard.
 *
 * Props:
 *   workspace        { id, name, is_personal, role }  — workspace object
 *   campaigns        Campaign[]                        — campaigns in this workspace
 *   userRole         string (optional)                 — override workspace.role
 *   onCreateCampaign function (optional)               — called when create button clicked
 *   collapsed        boolean (optional)                — controlled collapsed state
 *   isAdmin          boolean
 *   isViewer         boolean
 *   user             object
 *   onDelete         function(campaignId)
 *   allWorkspaces    Workspace[]
 *   onMove           function(campaignId, workspaceId)
 *   children         ReactNode (optional) — rendered inside body instead of default campaign list
 */
export default function WorkspaceSection({
  workspace,
  campaigns = [],
  userRole,
  onCreateCampaign,
  collapsed: controlledCollapsed,
  isAdmin,
  isViewer,
  user,
  onDelete,
  allWorkspaces = [],
  onMove,
  children,
  deletingId,
  hasMore = false,
  loadingMore = false,
  onLoadMore,
}) {
  const storageKey = `ws-collapsed-${workspace.id}`;
  const [internalOpen, setInternalOpen] = useState(
    () => localStorage.getItem(storageKey) !== "true"
  );

  // Support both controlled and uncontrolled collapse state
  const isControlled = controlledCollapsed !== undefined;
  const isOpen = isControlled ? !controlledCollapsed : internalOpen;

  const toggle = () => {
    if (isControlled) return; // controlled mode — caller manages state
    const next = !internalOpen;
    setInternalOpen(next);
    if (!next) {
      localStorage.setItem(storageKey, "true");
    } else {
      localStorage.removeItem(storageKey);
    }
  };

  const effectiveRole = userRole ?? workspace.role;
  const isCreator = effectiveRole === "creator";
  const isOrphaned = workspace.id === "__orphaned__";

  const handleCreateClick = (e) => {
    if (onCreateCampaign) {
      e.preventDefault();
      e.stopPropagation();
      onCreateCampaign(workspace);
    } else {
      e.stopPropagation();
    }
  };

  const handleRemove = async (campaignId) => {
    if (onDelete) onDelete(campaignId, workspace.id);
  };

  const handleMove = async (campaignId, workspaceId) => {
    if (onMove) onMove(campaignId, workspaceId);
  };

  return (
    <div className="workspace-section">
      <button
        type="button"
        className="workspace-section-header"
        onClick={toggle}
        aria-expanded={isOpen}
        aria-controls={`ws-body-${workspace.id}`}
      >
        <span className="workspace-section-toggle">{isOpen ? "▼" : "▶"}</span>
        <span className="workspace-section-icon" aria-hidden="true">
          {isOrphaned ? "⚠️" : workspace.is_personal ? "🏠" : "📁"}
        </span>
        <span className="workspace-section-name">{workspace.name}</span>
        {!isOrphaned && effectiveRole && (
          <span className={`workspace-role-badge workspace-role-badge--${effectiveRole}`}>
            {ROLE_LABELS[effectiveRole] ?? effectiveRole}
          </span>
        )}
        <span className="workspace-campaign-count">{campaigns.length}</span>
        {isCreator && !isOrphaned && (
          onCreateCampaign ? (
            <button
              type="button"
              className="btn btn-primary workspace-new-btn"
              onClick={handleCreateClick}
              aria-label={`Create campaign in ${workspace.name}`}
            >
              +
            </button>
          ) : (
            <Link
              to={`/workspaces/${workspace.id}/campaigns/new`}
              className="btn btn-primary workspace-new-btn"
              onClick={(e) => e.stopPropagation()}
              aria-label={`Create campaign in ${workspace.name}`}
            >
              +
            </Link>
          )
        )}
      </button>

      {isOpen && (
        <div className="workspace-section-body" id={`ws-body-${workspace.id}`}>
          {children ? (
            children
          ) : campaigns.length === 0 ? (
            <div className="workspace-empty-state">
              <p>No campaigns yet.</p>
              {isCreator && !isOrphaned && (
                onCreateCampaign ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onCreateCampaign(workspace)}
                  >
                    + Create Campaign
                  </button>
                ) : (
                  <Link to={`/workspaces/${workspace.id}/campaigns/new`} className="btn btn-primary">
                    + Create Campaign
                  </Link>
                )
              )}
            </div>
          ) : isOrphaned ? (
            <div className="campaign-list">
              {campaigns.map((c) => (
                <DefaultCampaignCard
                  key={c.id}
                  c={c}
                  isAdmin={isAdmin}
                  isViewer={isViewer}
                  user={user}
                  onDelete={handleRemove}
                  showAssign={isAdmin}
                  workspaces={allWorkspaces}
                  onMove={handleMove}
                  deletingId={deletingId}
                />
              ))}
            </div>
          ) : (
            <>
              {STATUS_GROUPS.map(({ label, statuses }) => {
                const group = campaigns.filter((c) => statuses.includes(c.status));
                if (group.length === 0) return null;
                return (
                  <div key={label} className="status-group">
                    <h4 className="status-group-label">{label}</h4>
                    <div className="campaign-list">
                      {group.map((c) => (
                        <DefaultCampaignCard
                          key={c.id}
                          c={c}
                          isAdmin={isAdmin}
                          isViewer={isViewer}
                          user={user}
                          onDelete={handleRemove}
                          showAssign={false}
                          workspaces={allWorkspaces}
                          onMove={handleMove}
                          deletingId={deletingId}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
              {hasMore && (
                <div className="workspace-load-more">
                  <button
                    type="button"
                    className="btn btn-outline"
                    disabled={loadingMore}
                    onClick={onLoadMore}
                    aria-label={`Load more campaigns in ${workspace.name}`}
                  >
                    {loadingMore ? "Loading…" : "Load more campaigns"}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Default campaign card — used when no custom children are passed
// ---------------------------------------------------------------------------
function getInitials(name) {
  if (!name?.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function DefaultCampaignCard({ c, isAdmin, isViewer, user, onDelete, showAssign, workspaces, onMove, deletingId }) {
  const [assigning, setAssigning] = useState(false);
  const isDraft = c.status === "draft";
  const campaignUrl = isDraft
    ? `/workspaces/${c.workspace_id}/campaigns/${c.id}/edit`
    : `/workspaces/${c.workspace_id}/campaigns/${c.id}`;

  const handleAssign = async (workspaceId) => {
    if (!workspaceId) return;
    setAssigning(true);
    try {
      await onMove(c.id, workspaceId);
    } finally {
      setAssigning(false);
    }
  };

  return (
    <div className="campaign-card card" data-status={c.status}>
      <div className="campaign-card-avatar">{getInitials(c.product_or_service)}</div>
      <div className="campaign-card-body">
        <Link to={campaignUrl} className="campaign-card-title">
          {c.product_or_service}
        </Link>
        <p className="campaign-card-goal">{c.goal}</p>
      </div>
      <div className="campaign-card-meta">
        <StatusBadge status={c.status} />
        {isDraft && (
          <Link
            to={campaignUrl}
            className="btn btn-outline"
            style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
          >
            Resume →
          </Link>
        )}
        {showAssign && (
          <select
            className="btn btn-outline"
            style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
            defaultValue=""
            disabled={assigning}
            onChange={(e) => handleAssign(e.target.value)}
            aria-label="Assign to workspace"
          >
            <option value="" disabled>Assign to workspace…</option>
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id}>{ws.name}</option>
            ))}
          </select>
        )}
        {(isAdmin || (!isViewer && c.owner_id === user?.id)) && (
          <button
            className="btn btn-outline"
            style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
            disabled={deletingId === c.id}
            onClick={() => onDelete(c.id)}
          >
            {deletingId === c.id ? "Deleting…" : isDraft ? "Discard" : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}
