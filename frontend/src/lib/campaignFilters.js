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
