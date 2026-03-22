import {
  DRAFT_STATUSES,
  IN_PROGRESS_STATUSES,
  AWAITING_APPROVAL_STATUSES,
  APPROVED_STATUSES,
  AWAITING_MY_ACTION_STATUSES,
} from "../constants/statusGroups";

/**
 * Apply a filter tab to the full campaign list.
 * Returns the subset of campaigns that match the active tab.
 */
export function applyFilter(campaigns, tabId, user, workspaces) {
  switch (tabId) {
    case "my_campaigns":
      return campaigns.filter((c) => c.owner_id === user?.id);

    case "drafts":
      return campaigns.filter((c) => DRAFT_STATUSES.includes(c.status));

    case "awaiting_my_action": {
      // Non-viewer workspace members or campaign owners whose campaigns are paused
      const nonViewerWsIds = new Set(
        (workspaces ?? []).filter((ws) => ws.role !== "viewer").map((ws) => ws.id)
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
export function matchesSearch(campaign, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return [
    campaign.product_or_service,
    campaign.goal,
    campaign.workspace_name,
    campaign.status?.replace(/_/g, " "),
  ].some((field) => field?.toLowerCase().includes(q));
}

// Status ordering for the "status" sort option.
const STATUS_ORDER = [
  ...DRAFT_STATUSES,
  ...IN_PROGRESS_STATUSES,
  ...AWAITING_APPROVAL_STATUSES,
  ...APPROVED_STATUSES,
];

/**
 * Sort a campaign list by the given sort key.
 * Returns a new sorted array (does not mutate the input).
 */
export function sortCampaigns(campaigns, sortBy) {
  const sorted = [...campaigns];
  switch (sortBy) {
    case "oldest":
      return sorted.sort(
        (a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0)
      );
    case "name_asc":
      return sorted.sort((a, b) =>
        (a.product_or_service ?? "").localeCompare(b.product_or_service ?? "")
      );
    case "name_desc":
      return sorted.sort((a, b) =>
        (b.product_or_service ?? "").localeCompare(a.product_or_service ?? "")
      );
    case "status": {
      return sorted.sort((a, b) => {
        const ai = STATUS_ORDER.indexOf(a.status);
        const bi = STATUS_ORDER.indexOf(b.status);
        return (ai === -1 ? STATUS_ORDER.length : ai) - (bi === -1 ? STATUS_ORDER.length : bi);
      });
    }
    case "newest":
    default:
      return sorted.sort(
        (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)
      );
  }
}
