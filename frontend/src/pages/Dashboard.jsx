import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listCampaigns, deleteCampaign } from "../api";
import { useUser } from "../UserContext";

const IN_PROGRESS_STATUSES = ["draft", "strategy", "content", "channel_planning", "analytics_setup", "review", "review_clarification", "content_revision", "clarification"];
const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];
const APPROVED_STATUSES = ["approved"];

function getInitials(name) {
  if (!name?.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export default function Dashboard({ events }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isViewer, isAdmin, user } = useUser();

  const load = async () => {
    setLoading(true);
    try {
      setCampaigns(await listCampaigns());
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Auto-refresh when a pipeline event arrives
  useEffect(() => {
    if (events.length > 0) load();
  }, [events.length]);

  const handleDelete = async (id) => {
    if (!confirm("Delete this campaign?")) return;
    await deleteCampaign(id);
    load();
  };

  if (loading && campaigns.length === 0) {
    return (
      <div className="loading">
        <span className="spinner" /> Loading campaigns…
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
      </div>

      <div className="section-header">
        <h2>Campaigns</h2>
        {!isViewer && (
          <Link to="/new" className="btn btn-primary">
            + New Campaign
          </Link>
        )}
      </div>

      <div className="campaign-list">
        {campaigns.map((c) => (
          <div key={c.id} className="campaign-card card" data-status={c.status}>
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
              {(isAdmin || (!isViewer && c.owner_id === user?.id)) && (
                <button
                  className="btn btn-outline"
                  style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                  onClick={() => handleDelete(c.id)}
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
