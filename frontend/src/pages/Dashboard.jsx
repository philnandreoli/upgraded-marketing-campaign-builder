import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listCampaigns, deleteCampaign, getUnresolvedCommentCount } from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";
import { useConfirm } from "../ConfirmDialogContext";
import { SkeletonCard, SkeletonStat, SkeletonFilterTabs } from "../components/Skeleton";
import WorkspaceSection from "../components/WorkspaceSection";
import FilterTabs from "../components/FilterTabs";
import SearchBar from "../components/SearchBar";
import SavedViews from "../components/SavedViews";
import SortDropdown from "../components/SortDropdown";
import Toast from "../components/Toast";
import useSavedViews from "../hooks/useSavedViews";
import { applyFilter, matchesSearch, sortCampaigns } from "../lib/campaignFilters";
import {
  DRAFT_STATUSES,
  IN_PROGRESS_STATUSES,
  AWAITING_APPROVAL_STATUSES,
  APPROVED_STATUSES,
  FILTER_TAB_STORAGE_KEY,
  SORT_OPTIONS,
  SORT_STORAGE_KEY,
} from "../constants/statusGroups";

const PAGE_SIZE = 50;

export default function Dashboard({ events }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [campaigns, setCampaigns] = useState([]);
  const [commentCounts, setCommentCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState({});
  const [deleting, setDeleting] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const pendingDeletesRef = useRef(new Set());
  const undoTimersRef = useRef({});
  const paginationRef = useRef({});
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
  const [sortBy, setSortBy] = useState(
    () => localStorage.getItem(SORT_STORAGE_KEY) ?? "newest"
  );
  const { isViewer, isAdmin, user } = useUser();
  const { workspaces } = useWorkspace();
  const { views, addView, removeView, renameView } = useSavedViews();
  const confirm = useConfirm();

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

  const handleSortChange = (value) => {
    setSortBy(value);
    localStorage.setItem(SORT_STORAGE_KEY, value);
  };

  // Clean up any pending debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const fetchCommentCounts = useCallback(async (campaignList) => {
    const counts = {};
    await Promise.all(
      campaignList.map((c) =>
        getUnresolvedCommentCount(c.workspace_id, c.id)
          .then((res) => { counts[c.id] = res.unresolved ?? 0; })
          .catch(() => { /* silent — leave count absent */ })
      )
    );
    setCommentCounts((prev) => ({ ...prev, ...counts }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch the first page of campaigns (including drafts) per workspace
      const results = await Promise.all(
        workspaces.map((ws) =>
          listCampaigns(ws.id, { includeDrafts: true, limit: PAGE_SIZE, offset: 0 })
            .then((res) => ({ wsId: ws.id, items: res.items, pagination: res.pagination }))
            .catch(() => ({ wsId: ws.id, items: [], pagination: { has_more: false, total_count: 0, offset: 0, limit: PAGE_SIZE } }))
        )
      );
      // Update pagination tracking per workspace
      const newPagination = {};
      for (const { wsId, pagination } of results) {
        newPagination[wsId] = {
          offset: pagination.offset + (pagination.returned_count ?? pagination.limit),
          hasMore: pagination.has_more,
          totalCount: pagination.total_count,
        };
      }
      paginationRef.current = newPagination;
      // Filter out campaigns currently in the soft-delete undo window
      const allItems = results.flatMap((r) => r.items);
      const visible = allItems.filter((c) => !pendingDeletesRef.current.has(c.id));
      setCampaigns(visible);

      // Fetch unresolved comment counts (non-blocking)
      fetchCommentCounts(visible);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [workspaces, fetchCommentCounts]);
  const loadMore = useCallback(async (workspaceId) => {
    const pg = paginationRef.current[workspaceId];
    if (!pg || !pg.hasMore) return;

    setLoadingMore((prev) => ({ ...prev, [workspaceId]: true }));
    try {
      const res = await listCampaigns(workspaceId, {
        includeDrafts: true,
        limit: PAGE_SIZE,
        offset: pg.offset,
      });
      paginationRef.current = {
        ...paginationRef.current,
        [workspaceId]: {
          offset: pg.offset + (res.pagination.returned_count ?? res.pagination.limit),
          hasMore: res.pagination.has_more,
          totalCount: res.pagination.total_count,
        },
      };
      const newItems = res.items.filter((c) => !pendingDeletesRef.current.has(c.id));
      setCampaigns((prev) => [...prev, ...newItems]);

      // Fetch unresolved comment counts for the new page
      fetchCommentCounts(newItems);
    } catch {
      /* silent */
    } finally {
      setLoadingMore((prev) => ({ ...prev, [workspaceId]: false }));
    }
  }, [fetchCommentCounts]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh when a pipeline event arrives
  useEffect(() => {
    if (events.length > 0) load();
  }, [events.length]);

  // Clean up any pending undo timers on unmount
  useEffect(() => {
    const timers = undoTimersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const handleDelete = async (id, workspaceId) => {
    const confirmed = await confirm({
      title: "Delete this campaign?",
      message: "This action cannot be undone.",
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;

    const campaign = campaigns.find((c) => c.id === id);
    if (!campaign) return;

    // Optimistically remove from local state
    pendingDeletesRef.current.add(id);
    setCampaigns((prev) => prev.filter((c) => c.id !== id));
    setDeleting(null);

    const notifId = `delete-${id}`;

    const executeDelete = async () => {
      delete undoTimersRef.current[notifId];
      // Dismiss toast before the API call
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
      try {
        await deleteCampaign(workspaceId, id);
      } catch {
        // Restore campaign if API call fails
        setCampaigns((prev) => {
          if (prev.find((c) => c.id === id)) return prev;
          return [...prev, campaign];
        });
      } finally {
        pendingDeletesRef.current.delete(id);
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
            pendingDeletesRef.current.delete(id);
            setCampaigns((prev) => {
              if (prev.find((c) => c.id === id)) return prev;
              return [...prev, campaign];
            });
            setNotifications((prev) => prev.filter((n) => n.id !== notifId));
          },
        },
      },
    ]);
  };

  const draftCount = useMemo(() => campaigns.filter((c) => DRAFT_STATUSES.includes(c.status)).length, [campaigns]);
  const inProgressCount = useMemo(() => campaigns.filter((c) => IN_PROGRESS_STATUSES.includes(c.status)).length, [campaigns]);
  const awaitingCount = useMemo(() => campaigns.filter((c) => AWAITING_APPROVAL_STATUSES.includes(c.status)).length, [campaigns]);
  const approvedCount = useMemo(() => campaigns.filter((c) => APPROVED_STATUSES.includes(c.status)).length, [campaigns]);
  const workspaceCount = workspaces.length;

  // Apply the active filter tab to narrow the campaign list
  const filteredCampaigns = useMemo(
    () => applyFilter(campaigns, activeFilter, user, workspaces),
    [campaigns, activeFilter, user, workspaces]
  );

  // Apply search query on top of the tab-filtered results, then sort
  const searchedCampaigns = useMemo(
    () => sortCampaigns(filteredCampaigns.filter((c) => matchesSearch(c, debouncedQuery)), sortBy),
    [filteredCampaigns, debouncedQuery, sortBy]
  );

  // Group searched campaigns by workspace_id; null workspace_id → orphaned
  const { campaignsByWorkspace, orphanedCampaigns } = useMemo(() => {
    const byWorkspace = {};
    const orphaned = [];
    for (const c of searchedCampaigns) {
      if (c.workspace_id) {
        if (!byWorkspace[c.workspace_id]) byWorkspace[c.workspace_id] = [];
        byWorkspace[c.workspace_id].push(c);
      } else {
        orphaned.push(c);
      }
    }
    return { campaignsByWorkspace: byWorkspace, orphanedCampaigns: orphaned };
  }, [searchedCampaigns]);

  // Determine whether any filter or search is active
  const isFiltered = activeFilter !== "all" || debouncedQuery.length > 0;

  // Sort workspaces: personal workspace first, then alphabetically
  const sortedWorkspaces = useMemo(
    () => [...workspaces].sort((a, b) => {
      if (a.is_personal && !b.is_personal) return -1;
      if (!a.is_personal && b.is_personal) return 1;
      return a.name.localeCompare(b.name);
    }),
    [workspaces]
  );

  let content;
  if (loading && campaigns.length === 0) {
    content = (
      <div>
        <div className="dashboard-stats">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonStat key={i} />
          ))}
        </div>
        <SkeletonFilterTabs />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  } else if (campaigns.length === 0) {
    const personalWorkspace = workspaces.find(
      (ws) => ws.is_personal && ws.role === "creator"
    );
    content = (
      <div className="empty-state">
        <div className="empty-state-icon">🚀</div>
        <h2 className="empty-state-title">No campaigns yet</h2>
        <p className="empty-state-body">
          Launch your first marketing campaign and let AI handle strategy,
          content, and channel planning for you.
        </p>
        {!isViewer && (
          <div className="empty-state-actions">
            <Link to="/workspaces" className="btn btn-primary">
              Browse Workspaces
            </Link>
            {personalWorkspace && (
              <Link
                to={`/workspaces/${personalWorkspace.id}/campaigns/new`}
                className="btn btn-outline"
              >
                Create Campaign
              </Link>
            )}
          </div>
        )}
      </div>
    );
  } else {
    content = (
      <div>
        {/* Stats hero strip — counts are clickable to activate the matching filter */}
        <div className="dashboard-stats">
          <button
            className={`stat-card stat-card--clickable${activeFilter === "all" ? " stat-card--active" : ""}`}
            onClick={() => handleFilterChange("all")}
            aria-label="Filter by Total"
          >
            <span className="stat-number stat-number--total">{campaigns.length}</span>
            <span className="stat-label">Total</span>
          </button>
          <button
            className={`stat-card stat-card--clickable${activeFilter === "drafts" ? " stat-card--active" : ""}`}
            onClick={() => handleFilterChange("drafts")}
            aria-label="Filter by Drafts"
          >
            <span className="stat-number stat-number--drafts">{draftCount}</span>
            <span className="stat-label">Drafts</span>
          </button>
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
            <span className="stat-number stat-number--workspaces">{workspaceCount}</span>
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
          <div className="section-header__controls">
            <SortDropdown
              options={SORT_OPTIONS}
              value={sortBy}
              onChange={handleSortChange}
              ariaLabel="Sort campaigns"
            />
            {loading && campaigns.length > 0 && (
              <span className="campaign-list-loading" aria-live="polite">
                <span className="spinner" />
                Refreshing…
              </span>
            )}
            {debouncedQuery && (
              <span className="search-result-count">
                Showing {searchedCampaigns.length} of {filteredCampaigns.length} campaign{filteredCampaigns.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
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
            {sortedWorkspaces
              .filter((ws) => !isFiltered || (campaignsByWorkspace[ws.id]?.length ?? 0) > 0)
              .map((ws) => (
              <WorkspaceSection
                key={ws.id}
                workspace={ws}
                campaigns={campaignsByWorkspace[ws.id] ?? []}
                commentCounts={commentCounts}
                isAdmin={isAdmin}
                isViewer={isViewer}
                user={user}
                onDelete={handleDelete}
                allWorkspaces={workspaces}
                deletingId={deleting}
                hasMore={!isFiltered && !!paginationRef.current[ws.id]?.hasMore}
                loadingMore={!!loadingMore[ws.id]}
                onLoadMore={() => loadMore(ws.id)}
              />
            ))}
            {/* Orphaned campaigns: admin only */}
            {isAdmin && orphanedCampaigns.length > 0 && (
              <WorkspaceSection
                workspace={{ id: "__orphaned__", name: "Orphaned Campaigns", is_personal: false, role: "creator" }}
                campaigns={orphanedCampaigns}
                commentCounts={commentCounts}
                isAdmin={isAdmin}
                isViewer={isViewer}
                user={user}
                onDelete={handleDelete}
                allWorkspaces={workspaces}
                deletingId={deleting}
              />
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      {content}
      <Toast events={events} notifications={notifications} />
    </>
  );
}

