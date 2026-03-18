const STATUS_LABELS = {
  draft: "Draft",
  strategy: "Strategy",
  content: "Content",
  channel_planning: "Channel Planning",
  analytics_setup: "Analytics Setup",
  review: "Review",
  review_clarification: "Review Clarification",
  content_revision: "Content Revision",
  clarification: "Clarification",
  content_approval: "Content Approval",
  awaiting_approval: "Awaiting Approval",
  approved: "Approved",
  rejected: "Rejected",
  manual_review_required: "Manual Review",
  pending: "Pending",
};

function toTitleCase(str) {
  return str.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function StatusBadge({ status, pulse }) {
  const label = STATUS_LABELS[status] ?? toTitleCase(status);
  return (
    <span className={`badge badge-${status}${pulse ? " badge-updated" : ""}`}>
      {label}
    </span>
  );
}
