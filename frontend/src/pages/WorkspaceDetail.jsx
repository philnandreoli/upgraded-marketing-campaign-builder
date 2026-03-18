import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getWorkspace,
  listWorkspaceCampaigns,
  deleteCampaign,
} from "../api";
import { useUser } from "../UserContext";
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

const POLL_INTERVAL_MS = 3000;

function getInitials(name) {
  if (!name?.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function CampaignCard({ c, isAdmin, isViewer, user, onDelete, workspaceId, deletingId }) {
  return (
    <div className="campaign-card card" data-status={c.status}>
      <div className="campaign-card-avatar">
        {getInitials(c.product_or_service)}
      </div>
      <div className="campaign-card-body">
        <Link to={`/workspaces/${workspaceId}/campaigns/${c.id}`} className="campaign-card-title">
          {c.product_or_service}
        </Link>
        <p className="campaign-card-goal">{c.goal}</p>
      </div>
      <div className="campaign-card-meta">
        <span className={`badge badge-${c.status}`}>{c.status.replace(/_/g, " ")}</span>
        {(isAdmin || (!isViewer && c.owner_id === user?.id)) && (
          <button
            className="btn btn-outline"
            style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
            disabled={deletingId === c.id}
            onClick={() => onDelete(c.id)}
          >
            {deletingId === c.id ? "Deleting…" : "Delete"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function WorkspaceDetail({ events = [] }) {
  const { id } = useParams();
  const { isAdmin, isViewer, user } = useUser();

  const [workspace, setWorkspace] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  // Fetch workspace detail
  useEffect(() => {
    setLoadingWs(true);
    getWorkspace(id)
      .then(setWorkspace)
      .catch((err) => setError(err.message))
      .finally(() => setLoadingWs(false));
  }, [id]);

  // Fetch campaigns
  const loadCampaigns = useCallback(async () => {
    try {
      setCampaigns(await listWorkspaceCampaigns(id));
    } catch {
      /* silent */
    } finally {
      setLoadingCampaigns(false);
    }
  }, [id]);

  useEffect(() => {
    setLoadingCampaigns(true);
    loadCampaigns();
  }, [loadCampaigns]);

  // Poll campaigns every 3s
  useEffect(() => {
    const timer = setInterval(loadCampaigns, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [loadCampaigns]);

  // Refresh campaigns when a WebSocket event arrives
  useEffect(() => {
    if (events.length > 0) loadCampaigns();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  const handleDelete = async (campaignId) => {
    if (!confirm("Delete this campaign?")) return;
    setDeleting(campaignId);
    try {
      await deleteCampaign(id, campaignId);
      loadCampaigns();
    } finally {
      setDeleting(null);
    }
  };

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
        <Link to="/workspaces" className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          ← Back to Workspaces
        </Link>
      </div>
    );
  }

  if (!workspace) return null;

  const isCreatorOrAdmin = isAdmin || workspace.role === "creator";

  return (
    <div>
      {/* ── Workspace Header ─────────────────────────────────────────── */}
      <div className="ws-detail-header card">
        <div className="ws-detail-header-top">
          <div className="ws-detail-title-row">
            <span className="ws-detail-icon" aria-hidden="true">{workspace.is_personal ? "🏠" : "📁"}</span>
            <h2 className="ws-detail-name">{workspace.name}</h2>
            {workspace.is_personal && (
              <span className="ws-card-personal-badge">Personal</span>
            )}
            {workspace.role && (
              <span className={`workspace-role-badge workspace-role-badge--${workspace.role}`}>
                {ROLE_LABELS[workspace.role] ?? workspace.role}
              </span>
            )}
          </div>
          <div className="ws-detail-actions">
            {isCreatorOrAdmin && (
              <Link
                to={`/workspaces/${workspace.id}/settings`}
                className="btn btn-outline"
              >
                ⚙ Settings
              </Link>
            )}
          </div>
        </div>
        {workspace.description && (
          <p className="ws-detail-description">{workspace.description}</p>
        )}
        {workspace.owner_display_name && (
          <p className="ws-detail-owner">
            Owner: <strong>{workspace.owner_display_name}</strong>
          </p>
        )}
      </div>

      {/* ── Campaigns Section ─────────────────────────────────────────── */}
      <div className="section-header" style={{ marginTop: "1.5rem" }}>
        <h2>Campaigns</h2>
        {isCreatorOrAdmin && (
          <Link to={`/workspaces/${workspace.id}/campaigns/new`} className="btn btn-primary">
            + Create Campaign
          </Link>
        )}
      </div>

      {loadingCampaigns && campaigns.length === 0 ? (
        <div>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="workspace-empty-state card">
          <p>No campaigns in this workspace yet.</p>
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
                      onDelete={handleDelete}
                      workspaceId={id}
                      deletingId={deleting}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </>
      )}

    </div>
  );
}
