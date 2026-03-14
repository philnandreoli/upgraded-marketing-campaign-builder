import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listCampaigns, deleteCampaign } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";
import { SkeletonCard } from "../components/Skeleton";
import WorkspaceSection from "../components/WorkspaceSection";

const IN_PROGRESS_STATUSES = ["draft", "strategy", "content", "channel_planning", "analytics_setup", "review", "review_clarification", "content_revision", "clarification"];
const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];
const APPROVED_STATUSES = ["approved"];

export default function Dashboard({ events }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isViewer, isAdmin, user } = useUser();
  const { workspaces } = useWorkspace();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch campaigns for each workspace and flatten into a single list
      const campaignArrays = await Promise.all(
        workspaces.map((ws) => listCampaigns(ws.id).catch(() => []))
      );
      setCampaigns(campaignArrays.flat());
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [workspaces]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh when a pipeline event arrives
  useEffect(() => {
    if (events.length > 0) load();
  }, [events.length]);

  const handleDelete = async (id, workspaceId) => {
    if (!confirm("Delete this campaign?")) return;
    await deleteCampaign(workspaceId, id);
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
    return a.name.localeCompare(b.name);
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
            + Create Campaign
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
          />
        )}
      </div>
    </div>
  );
}
