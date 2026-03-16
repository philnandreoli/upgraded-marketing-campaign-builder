// Shared status group constants used by Dashboard filter tabs and workspace sections.

// Draft = wizard-incomplete campaigns that have not yet been launched.
export const DRAFT_STATUSES = ["draft"];

export const IN_PROGRESS_STATUSES = [
  "strategy",
  "content",
  "channel_planning",
  "analytics_setup",
  "review",
  "review_clarification",
  "content_revision",
  "clarification",
];

export const AWAITING_APPROVAL_STATUSES = ["content_approval", "awaiting_approval"];

export const APPROVED_STATUSES = ["approved"];

export const MANUAL_REVIEW_STATUSES = ["manual_review_required"];

// Statuses where the campaign is paused waiting for user action
export const AWAITING_MY_ACTION_STATUSES = ["clarification", "content_approval"];

// Dashboard filter tab definitions — order determines render order
export const FILTER_TABS = [
  { id: "all", label: "All" },
  { id: "my_campaigns", label: "My Campaigns" },
  { id: "drafts", label: "Drafts" },
  { id: "awaiting_my_action", label: "Awaiting My Action" },
  { id: "in_progress", label: "In Progress" },
  { id: "needs_approval", label: "Needs Approval" },
  { id: "approved", label: "Approved" },
];

export const FILTER_TAB_STORAGE_KEY = "dashboard-active-filter";
