import { useCallback, useEffect, useRef, useState } from "react";
import { listCampaigns, deleteCampaign } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";
import { SkeletonCard } from "../components/Skeleton";
import WorkspaceSection from "../components/WorkspaceSection";
import FilterTabs from "../components/FilterTabs";
import SearchBar from "../components/SearchBar";
import {
  IN_PROGRESS_STATUSES,
  AWAITING_APPROVAL_STATUSES,
  APPROVED_STATUSES,
  MANUAL_REVIEW_STATUSES,
  AWAITING_MY_ACTION_STATUSES,
  FILTER_TAB_STORAGE_KEY,
} from "../constants/statusGroups";

/**
 * Apply a filter tab to the full campaign list.
 * Returns the subset of campaigns that match the active tab.
 */
function applyFilter(campaigns, tabId, user, workspaces) {
  switch (tabId) {
    case "my_campaigns":
      return campaigns.filter((c) => c.owner_id === user?.id);

    case "awaiting_my_action": {
      // Non-viewer workspace members or campaign owners whose campaigns are paused
      const nonViewerWsIds = new Set(
        workspaces.filter((ws) => ws.role !== "viewer").map((ws) => ws.id)
      );
      return campaigns.filter(
        (c) =>
          AWAITING_MY_ACTION_STATUSES.includes(c.status) &&
          (c.owner_id === user?.id || nonViewerWsIds.has(c.workspace_id))
      );
    }

    case "in_progress":
      return campaigns.filter((c) => IN_PROGRESS_STATUSES.includes(c.status));

    case "needs_approval":
      return campaigns.filter((c) => AWAITING_APPROVAL_STATUSES.includes(c.status));

    case "manual_review":
      return campaigns.filter((c) => MANUAL_REVIEW_STATUSES.includes(c.status));

    case "approved":
      return campaigns.filter((c) => APPROVED_STATUSES.includes(c.status));

    default: // "all"
      return campaigns;
  }
}

/**
 * Match a campaign against a search query across key text fields.
 * Case-insensitive; returns true if any field contains the query.
 */
function matchesSearch(campaign, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return [
    campaign.product_or_service,
    campaign.goal,
    campaign.workspace_name,
    campaign.status?.replace(/_/g, " "),
  ].some((field) => field?.toLowerCase().includes(q));
}

export default function Dashboard({ events }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState(
    () => localStorage.getItem(FILTER_TAB_STORAGE_KEY) ?? "all"
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef(null);
  const { isViewer, isAdmin, user } = useUser();
  const { workspaces } = useWorkspace();

  const handleFilterChange = (tabId) => {
    setActiveFilter(tabId);
    localStorage.setItem(FILTER_TAB_STORAGE_KEY, tabId);
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
          <p className="empty-state-body">
            Select a workspace to create your first campaign.
          </p>
        )}
      </div>
    );
  }

  const inProgressCount = campaigns.filter((c) => IN_PROGRESS_STATUSES.includes(c.status)).length;
  const awaitingCount = campaigns.filter((c) => AWAITING_APPROVAL_STATUSES.includes(c.status)).length;
  const approvedCount = campaigns.filter((c) => APPROVED_STATUSES.includes(c.status)).length;
  const workspaceCount = workspaces.length;

  // Apply the active filter tab to narrow the campaign list
  const filteredCampaigns = applyFilter(campaigns, activeFilter, user, workspaces);

  // Apply search query on top of the tab-filtered results
  const searchedCampaigns = filteredCampaigns.filter((c) => matchesSearch(c, debouncedQuery));

  // Group searched campaigns by workspace_id; null workspace_id → orphaned
  const campaignsByWorkspace = {};
  const orphanedCampaigns = [];
  for (const c of searchedCampaigns) {
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
      {/* Stats hero strip — counts are clickable to activate the matching filter */}
      <div className="dashboard-stats">
        <div className="stat-card">
          <span className="stat-number">{campaigns.length}</span>
          <span className="stat-label">Total</span>
        </div>
        <button
          className={`stat-card stat-card--clickable${activeFilter === "in_progress" ? " stat-card--active" : ""}`}
          onClick={() => handleFilterChange("in_progress")}
          aria-label="Filter by In Progress"
        >
          <span className="stat-number stat-number--progress">{inProgressCount}</span>
          <span className="stat-label">In Progress</span>
        </button>
        <button
          className={`stat-card stat-card--clickable${activeFilter === "needs_approval" ? " stat-card--active" : ""}`}
          onClick={() => handleFilterChange("needs_approval")}
          aria-label="Filter by Awaiting Approval"
        >
          <span className="stat-number stat-number--warning">{awaitingCount}</span>
          <span className="stat-label">Awaiting Approval</span>
        </button>
        <button
          className={`stat-card stat-card--clickable${activeFilter === "approved" ? " stat-card--active" : ""}`}
          onClick={() => handleFilterChange("approved")}
          aria-label="Filter by Approved"
        >
          <span className="stat-number stat-number--success">{approvedCount}</span>
          <span className="stat-label">Approved</span>
        </button>
        <div className="stat-card">
          <span className="stat-number">{workspaceCount}</span>
          <span className="stat-label">Workspaces</span>
        </div>
      </div>

      {/* Filter tab bar */}
      <FilterTabs activeTab={activeFilter} onTabChange={handleFilterChange} />

      {/* Search bar */}
      <SearchBar
        value={searchQuery}
        onChange={handleSearchChange}
        onClear={handleSearchClear}
      />

      <div className="section-header">
        <h2>Campaigns</h2>
        {debouncedQuery && (
          <span className="search-result-count">
            Showing {searchedCampaigns.length} of {filteredCampaigns.length} campaign{filteredCampaigns.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {searchedCampaigns.length === 0 ? (
        <div id="campaign-tabpanel" role="tabpanel" className="empty-state">
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
        <div id="campaign-tabpanel" role="tabpanel" className="workspace-list">
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
      )}
    </div>
  );
}
