import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listCampaigns, deleteCampaign, moveCampaign } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";
import { SkeletonCard } from "../components/Skeleton";

const IN_PROGRESS_STATUSES = ["draft", "strategy", "content", "channel_planning", "analytics_setup", "review", "review_clarification", "content_revision", "clarification"];
const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];
const APPROVED_STATUSES = ["approved"];

const STATUS_GROUPS = [
  { label: "In Progress", statuses: IN_PROGRESS_STATUSES },
  { label: "Awaiting Approval", statuses: AWAITING_APPROVAL_STATUSES },
  { label: "Approved", statuses: APPROVED_STATUSES },
];

const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

function getInitials(name) {
  if (!name?.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function CampaignCard({ c, isAdmin, isViewer, user, onDelete, showAssign, workspaces, onMove }) {
  const [assigning, setAssigning] = useState(false);

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
      <div className="campaign-card-avatar">
        {getInitials(c.product_or_service)}
      </div>
      <div className="campaign-card-body">
        <Link to={`/campaign/${c.id}`} className="campaign-card-title">
          {c.product_or_service}
        </Link>
        <p className="campaign-card-goal">{c.goal}</p>
      </div>
      <div className="campaign-card-meta">
        <span className={`badge badge-${c.status}`}>{c.status.replace(/_/g, " ")}</span>
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
            onClick={() => onDelete(c.id)}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

function WorkspaceSection({ workspace, campaigns, isAdmin, isViewer, user, onDelete, allWorkspaces, onMove }) {
  const storageKey = `ws-collapsed-${workspace.id}`;
  const [isOpen, setIsOpen] = useState(
    () => localStorage.getItem(storageKey) !== "true"
  );

  const toggle = () => {
    const next = !isOpen;
    setIsOpen(next);
    if (!next) {
      localStorage.setItem(storageKey, "true");
    } else {
      localStorage.removeItem(storageKey);
    }
  };

  const isCreator = workspace.role === "creator";
  const isOrphaned = workspace.id === "__orphaned__";

  return (
    <div className="workspace-section">
      <button
        type="button"
        className="workspace-section-header"
        onClick={toggle}
        aria-expanded={isOpen}
      >
        <span className="workspace-section-toggle">{isOpen ? "▼" : "▶"}</span>
        <span className="workspace-section-icon">{isOrphaned ? "⚠️" : "📁"}</span>
        <span className="workspace-section-name">{workspace.name}</span>
        {!isOrphaned && (
          <span className={`workspace-role-badge workspace-role-badge--${workspace.role}`}>
            {ROLE_LABELS[workspace.role] ?? workspace.role}
          </span>
        )}
        <span className="workspace-campaign-count">{campaigns.length}</span>
        {isCreator && !isOrphaned && (
          <Link
            to={`/new?workspace=${workspace.id}`}
            className="btn btn-primary workspace-new-btn"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Create campaign in ${workspace.name}`}
          >
            +
          </Link>
        )}
      </button>

      {isOpen && (
        <div className="workspace-section-body">
          {campaigns.length === 0 ? (
            <div className="workspace-empty-state">
              <p>No campaigns yet.</p>
              {isCreator && (
                <Link to={`/new?workspace=${workspace.id}`} className="btn btn-primary">
                  + Create Campaign
                </Link>
              )}
            </div>
          ) : isOrphaned ? (
            <div className="campaign-list">
              {campaigns.map((c) => (
                <CampaignCard
                  key={c.id}
                  c={c}
                  isAdmin={isAdmin}
                  isViewer={isViewer}
                  user={user}
                  onDelete={onDelete}
                  showAssign={isAdmin}
                  workspaces={allWorkspaces}
                  onMove={onMove}
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
                        <CampaignCard
                          key={c.id}
                          c={c}
                          isAdmin={isAdmin}
                          isViewer={isViewer}
                          user={user}
                          onDelete={onDelete}
                          showAssign={false}
                          workspaces={allWorkspaces}
                          onMove={onMove}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function Dashboard({ events }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isViewer, isAdmin, user } = useUser();
  const { workspaces } = useWorkspace();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCampaigns(await listCampaigns());
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh when a pipeline event arrives
  useEffect(() => {
    if (events.length > 0) load();
  }, [events.length]);

  const handleDelete = async (id) => {
    if (!confirm("Delete this campaign?")) return;
    await deleteCampaign(id);
    load();
  };

  const handleMove = async (campaignId, workspaceId) => {
    await moveCampaign(campaignId, workspaceId);
    load();
  };

  if (loading && campaigns.length === 0) {
    return (
      <div>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (campaigns.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🚀</div>
        <h2 className="empty-state-title">No campaigns yet</h2>
        <p className="empty-state-body">
          Launch your first marketing campaign and let AI handle strategy,
          content, and channel planning for you.
        </p>
        {!isViewer && (
          <Link to="/new" className="btn btn-primary">
            + Create your first campaign
          </Link>
        )}
      </div>
    );
  }

  const inProgressCount = campaigns.filter((c) => IN_PROGRESS_STATUSES.includes(c.status)).length;
  const awaitingCount = campaigns.filter((c) => AWAITING_APPROVAL_STATUSES.includes(c.status)).length;
  const approvedCount = campaigns.filter((c) => APPROVED_STATUSES.includes(c.status)).length;
  const workspaceCount = workspaces.length;

  // Group campaigns by workspace_id; null workspace_id → orphaned
  const campaignsByWorkspace = {};
  const orphanedCampaigns = [];
  for (const c of campaigns) {
    if (c.workspace_id) {
      if (!campaignsByWorkspace[c.workspace_id]) campaignsByWorkspace[c.workspace_id] = [];
      campaignsByWorkspace[c.workspace_id].push(c);
    } else {
      orphanedCampaigns.push(c);
    }
  }

  // Sort workspaces: personal workspace first, then alphabetically
  const sortedWorkspaces = [...workspaces].sort((a, b) => {
    if (a.is_personal && !b.is_personal) return -1;
    if (!a.is_personal && b.is_personal) return 1;
    return 0;
  });

  return (
    <div>
      {/* Stats hero strip */}
      <div className="dashboard-stats">
        <div className="stat-card">
          <span className="stat-number">{campaigns.length}</span>
          <span className="stat-label">Total</span>
        </div>
        <div className="stat-card">
          <span className="stat-number stat-number--progress">{inProgressCount}</span>
          <span className="stat-label">In Progress</span>
        </div>
        <div className="stat-card">
          <span className="stat-number stat-number--warning">{awaitingCount}</span>
          <span className="stat-label">Awaiting Approval</span>
        </div>
        <div className="stat-card">
          <span className="stat-number stat-number--success">{approvedCount}</span>
          <span className="stat-label">Approved</span>
        </div>
        <div className="stat-card">
          <span className="stat-number">{workspaceCount}</span>
          <span className="stat-label">Workspaces</span>
        </div>
      </div>

      <div className="section-header">
        <h2>Campaigns</h2>
        {!isViewer && (
          <Link to="/new" className="btn btn-primary">
            + New Campaign
          </Link>
        )}
      </div>

      <div className="workspace-list">
        {sortedWorkspaces.map((ws) => (
          <WorkspaceSection
            key={ws.id}
            workspace={ws}
            campaigns={campaignsByWorkspace[ws.id] ?? []}
            isAdmin={isAdmin}
            isViewer={isViewer}
            user={user}
            onDelete={handleDelete}
            allWorkspaces={workspaces}
            onMove={handleMove}
          />
        ))}
        {/* Orphaned campaigns: admin only */}
        {isAdmin && orphanedCampaigns.length > 0 && (
          <WorkspaceSection
            workspace={{ id: "__orphaned__", name: "Orphaned Campaigns", is_personal: false, role: "creator" }}
            campaigns={orphanedCampaigns}
            isAdmin={isAdmin}
            isViewer={isViewer}
            user={user}
            onDelete={handleDelete}
            allWorkspaces={workspaces}
            onMove={handleMove}
          />
        )}
      </div>
    </div>
  );
}
