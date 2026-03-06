const STAGES = [
  { key: "draft",             label: "Draft",    dataField: null },
  { key: "strategy",          label: "Strategy", dataField: "strategy" },
  { key: "content",           label: "Content",  dataField: "content" },
  { key: "channel_planning",  label: "Channels", dataField: "channel_plan" },
  { key: "analytics_setup",   label: "Analytics", dataField: "analytics_plan" },
  { key: "review",            label: "Review",   dataField: "review" },
  { key: "content_revision",  label: "Revision", dataField: "content_revision_count" },
  { key: "content_approval",  label: "Approval", dataField: null },
];

const ORDER = STAGES.map((s) => s.key);

/**
 * Returns true when the given stage has produced output data on the campaign,
 * meaning it has genuinely completed rather than just being behind the current
 * status index.
 */
function stageHasOutput(stage, campaign) {
  if (!campaign) return false;
  if (stage.key === "content_approval") {
    return campaign.status === "approved" || campaign.status === "rejected";
  }
  if (stage.key === "content_revision") {
    return (campaign.content_revision_count ?? 0) > 0;
  }
  if (!stage.dataField) return false;
  return campaign[stage.dataField] !== null && campaign[stage.dataField] !== undefined;
}

export default function PipelineProgress({ campaign }) {
  const status = campaign?.status ?? "";
  const currentIdx = ORDER.indexOf(status);

  // If approved/rejected/manual_review_required show all as completed
  const isTerminal = status === "approved" || status === "rejected" || status === "manual_review_required";

  return (
    <div className="pipeline-steps">
      {STAGES.map((stage, i) => {
        const hasOutput = stageHasOutput(stage, campaign);
        let cls = "pipeline-step";
        if (isTerminal) cls += " completed";
        else if (hasOutput) cls += " completed";
        else if (!stage.dataField && i < currentIdx) cls += " completed";
        else if (i === currentIdx) cls += " active";
        return (
          <div key={stage.key} className={cls}>
            {stage.label}
          </div>
        );
      })}
    </div>
  );
}
