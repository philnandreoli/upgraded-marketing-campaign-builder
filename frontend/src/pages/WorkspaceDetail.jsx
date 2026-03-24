import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getWorkspace,
  listWorkspaceCampaigns,
  deleteCampaign,
} from "../api";
import { useUser } from "../UserContext";
import { useConfirm } from "../ConfirmDialogContext";
import { SkeletonCard } from "../components/Skeleton";
import StatusBadge from "../components/StatusBadge.jsx";
import FilterTabs from "../components/FilterTabs.jsx";
import SearchBar from "../components/SearchBar.jsx";
import Toast from "../components/Toast.jsx";
import { applyFilter, matchesSearch } from "../lib/campaignFilters";
import usePolling from "../hooks/usePolling";

const IN_PROGRESS_STATUSES = ["draft", "strategy", "content", "channel_planning", "analytics_setup", "review", "review_clarification", "content_revision", "clarification"];
const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];
const APPROVED_STATUSES = ["approved"];

const STATUS_GROUPS = [
  { label: "In Progress", statuses: IN_PROGRESS_STATUSES },
  { label: "Awaiting Approval", statuses: AWAITING_APPROVAL_STATUSES },
  { label: "Approved", statuses: APPROVED_STATUSES },
];

const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

const POLL_INTERVAL_MS = 20000;

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
        <StatusBadge status={c.status} />
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
  const confirm = useConfirm();

  const [workspace, setWorkspace] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const pendingDeletesRef = useRef(new Set());
  const undoTimersRef = useRef({});

  const [activeFilter, setActiveFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef(null);

  const handleFilterChange = (tabId) => {
    setActiveFilter(tabId);
  };

  const handleSearchChange = (value) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value);
    }, 300);
  };

  const handleSearchClear = () => {
    setSearchQuery("");
    setDebouncedQuery("");
    if (debounceRef.current) clearTimeout(debounceRef.current);
  };

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
      const res = await listWorkspaceCampaigns(id);
      const items = res.items ?? res;
      // Filter out campaigns currently in the soft-delete undo window
      setCampaigns(items.filter((c) => !pendingDeletesRef.current.has(c.id)));
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

  // Poll campaigns with visibility-aware interval
  usePolling(loadCampaigns, POLL_INTERVAL_MS);

  // Refresh campaigns when a WebSocket event arrives
  useEffect(() => {
    if (events.length > 0) loadCampaigns();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  // Clean up any pending undo timers on unmount
  useEffect(() => {
    const timers = undoTimersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleDelete = async (campaignId) => {
    const confirmed = await confirm({
      title: "Delete this campaign?",
      message: "This action cannot be undone.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;

    const campaign = campaigns.find((c) => c.id === campaignId);
    if (!campaign) return;

    // Optimistically remove from local state
    pendingDeletesRef.current.add(campaignId);
    setCampaigns((prev) => prev.filter((c) => c.id !== campaignId));
    setDeleting(null);

    const notifId = `delete-${campaignId}`;

    const executeDelete = async () => {
      delete undoTimersRef.current[notifId];
      // Dismiss toast before the API call
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
      try {
        await deleteCampaign(id, campaignId);
      } catch {
        // Restore campaign if API call fails
        setCampaigns((prev) => {
          if (prev.find((c) => c.id === campaignId)) return prev;
          return [...prev, campaign];
        });
      } finally {
        pendingDeletesRef.current.delete(campaignId);
      }
    };

    undoTimersRef.current[notifId] = setTimeout(executeDelete, 5000);

    setNotifications((prev) => [
      ...prev,
      {
        id: notifId,
        icon: "🗑️",
        stage: "Campaign deleted",
        message: null,
        action: {
          label: "Undo",
          onClick: () => {
            clearTimeout(undoTimersRef.current[notifId]);
            delete undoTimersRef.current[notifId];
            pendingDeletesRef.current.delete(campaignId);
            setCampaigns((prev) => {
              if (prev.find((c) => c.id === campaignId)) return prev;
              return [...prev, campaign];
            });
            setNotifications((prev) => prev.filter((n) => n.id !== notifId));
          },
        },
      },
    ]);
  };

  // Apply filter tab and search to the campaign list
  const filteredCampaigns = applyFilter(campaigns, activeFilter, user);
  const searchedCampaigns = filteredCampaigns.filter((c) => matchesSearch(c, debouncedQuery));

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
            <Link
              to={`/workspaces/${workspace.id}/calendar`}
              className="btn btn-outline"
            >
              📅 Calendar
            </Link>
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
          <FilterTabs activeTab={activeFilter} onTabChange={handleFilterChange} />
          <SearchBar
            value={searchQuery}
            onChange={handleSearchChange}
            onClear={handleSearchClear}
          />

          {debouncedQuery && (
            <span className="search-result-count">
              Showing {searchedCampaigns.length} of {filteredCampaigns.length} campaign{filteredCampaigns.length !== 1 ? "s" : ""}
            </span>
          )}

          {searchedCampaigns.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔍</div>
              {debouncedQuery ? (
                <>
                  <h2 className="empty-state-title">No campaigns match your search</h2>
                  <p className="empty-state-body">
                    No results for &ldquo;{debouncedQuery}&rdquo;.{" "}
                    <button className="empty-state-reset" onClick={handleSearchClear}>
                      Clear search
                    </button>{" "}
                    or try a different term.
                  </p>
                </>
              ) : (
                <>
                  <h2 className="empty-state-title">No campaigns match this filter</h2>
                  <p className="empty-state-body">
                    Try selecting a different filter or{" "}
                    <button className="empty-state-reset" onClick={() => handleFilterChange("all")}>
                      view all campaigns
                    </button>
                    .
                  </p>
                </>
              )}
            </div>
          ) : (
            STATUS_GROUPS.map(({ label, statuses }) => {
              const group = searchedCampaigns.filter((c) => statuses.includes(c.status));
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
            })
          )}
        </>
      )}

      <Toast events={events} notifications={notifications} />
    </div>
  );
}
