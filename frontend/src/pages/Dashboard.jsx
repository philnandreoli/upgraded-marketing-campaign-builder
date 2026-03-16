import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCampaigns, deleteCampaign } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";
import { SkeletonCard } from "../components/Skeleton";
import WorkspaceSection from "../components/WorkspaceSection";
import FilterTabs from "../components/FilterTabs";
import SearchBar from "../components/SearchBar";
import SavedViews from "../components/SavedViews";
import useSavedViews from "../hooks/useSavedViews";
import {
  IN_PROGRESS_STATUSES,
  AWAITING_APPROVAL_STATUSES,
  APPROVED_STATUSES,
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [campaigns, setCampaigns] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState(
    () =>
      searchParams.get("status") ??
      localStorage.getItem(FILTER_TAB_STORAGE_KEY) ??
      "all"
  );
  const initialSearch = searchParams.get("q") ?? "";
  const [searchQuery, setSearchQuery] = useState(initialSearch);
  const [debouncedQuery, setDebouncedQuery] = useState(initialSearch);
  const debounceRef = useRef(null);
  const { isViewer, isAdmin, user } = useUser();
  const { workspaces } = useWorkspace();
  const { views, addView, removeView, renameView } = useSavedViews();

  const updateSearchParams = (filter, query) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (filter === "all") {
          next.delete("status");
        } else {
          next.set("status", filter);
        }
        if (query) {
          next.set("q", query);
        } else {
          next.delete("q");
        }
        return next;
      },
      { replace: true }
    );
  };

  const handleFilterChange = (tabId) => {
    setActiveFilter(tabId);
    localStorage.setItem(FILTER_TAB_STORAGE_KEY, tabId);
    updateSearchParams(tabId, debouncedQuery);
  };

  const handleSearchChange = (value) => {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value);
      updateSearchParams(activeFilter, value);
    }, 300);
  };

  const handleSearchClear = () => {
    setSearchQuery("");
    setDebouncedQuery("");
    if (debounceRef.current) clearTimeout(debounceRef.current);
    updateSearchParams(activeFilter, "");
  };

  const handleApplyView = (filter, search) => {
    setActiveFilter(filter);
    localStorage.setItem(FILTER_TAB_STORAGE_KEY, filter);
    setSearchQuery(search);
    setDebouncedQuery(search);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    updateSearchParams(filter, search);
  };

  // Clean up any pending debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch all campaigns including drafts, then split on the frontend
      const allArrays = await Promise.all(
        workspaces.map((ws) => listCampaigns(ws.id, { includeDrafts: true }).catch(() => []))
      );
      const all = allArrays.flat();
      setCampaigns(all.filter((c) => c.status !== "draft"));
      setDrafts(all.filter((c) => c.status === "draft"));
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

  if (loading && campaigns.length === 0 && drafts.length === 0) {
    return (
      <div>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (campaigns.length === 0 && drafts.length === 0) {
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

  // Determine whether any filter or search is active
  const isFiltered = activeFilter !== "all" || debouncedQuery.length > 0;

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

      {/* Saved views: system presets + user-created views */}
      <SavedViews
        activeFilter={activeFilter}
        searchQuery={debouncedQuery}
        views={views}
        onApply={handleApplyView}
        onAdd={addView}
        onRemove={removeView}
        onRename={renameView}
      />

      <div className="section-header">
        <h2>Campaigns</h2>
        {debouncedQuery && (
          <span className="search-result-count">
            Showing {searchedCampaigns.length} of {filteredCampaigns.length} campaign{filteredCampaigns.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Drafts section — shown when user has drafts in progress */}
      {!isViewer && drafts.length > 0 && (
        <div style={{ marginBottom: "1.5rem" }}>
          <div className="section-header" style={{ marginBottom: "0.5rem" }}>
            <h3 style={{ fontSize: "var(--text-base)", color: "var(--color-text-muted)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>📝</span> Drafts
              <span style={{ fontSize: "var(--text-xs)", background: "var(--color-surface-2)", border: "1px solid var(--color-border)", borderRadius: "999px", padding: "0.1rem 0.5rem", color: "var(--color-text-dim)" }}>
                {drafts.length}
              </span>
            </h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {drafts.map((draft) => {
              const ws = workspaces.find((w) => w.id === draft.workspace_id);
              const editUrl = ws
                ? `/workspaces/${encodeURIComponent(ws.id)}/campaigns/${encodeURIComponent(draft.id)}/edit`
                : null;
              const stepLabels = ["Workspace", "Campaign Basics", "Budget & Timeline", "Channels", "Additional Details", "Review & Launch"];
              const stepLabel = stepLabels[draft.wizard_step ?? 0] ?? "Campaign Basics";
              return (
                <div key={draft.id} className="card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", marginBottom: 0, padding: "0.85rem 1.25rem" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: "var(--text-sm)", color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {draft.product_or_service}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", color: "var(--color-text-dim)", marginTop: "0.15rem" }}>
                      {ws ? ws.name : "Unknown workspace"} · Step: {stepLabel}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                    {editUrl && (
                      <Link to={editUrl} className="btn btn-outline" style={{ fontSize: "var(--text-xs)", padding: "0.3rem 0.75rem" }}>
                        Resume →
                      </Link>
                    )}
                    <button
                      className="btn btn-outline"
                      style={{ fontSize: "var(--text-xs)", padding: "0.3rem 0.75rem", color: "var(--color-danger)", borderColor: "var(--color-danger)" }}
                      onClick={() => handleDelete(draft.id, draft.workspace_id)}
                    >
                      Discard
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
          {sortedWorkspaces
            .filter((ws) => !isFiltered || (campaignsByWorkspace[ws.id]?.length ?? 0) > 0)
            .map((ws) => (
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
