const STAGES = [
  { key: "draft", label: "Draft" },
  { key: "strategy", label: "Strategy" },
  { key: "content", label: "Content" },
  { key: "channel_planning", label: "Channels" },
  { key: "analytics_setup", label: "Analytics" },
  { key: "review", label: "Review" },
  { key: "content_revision", label: "Revision" },
  { key: "content_approval", label: "Approval" },
];

const ORDER = STAGES.map((s) => s.key);

export default function PipelineProgress({ status }) {
  const currentIdx = ORDER.indexOf(status);

  // If approved/rejected show all as completed
  const isTerminal = status === "approved" || status === "rejected";

  return (
    <div className="pipeline-steps">
      {STAGES.map((stage, i) => {
        let cls = "pipeline-step";
        if (isTerminal) cls += " completed";
        else if (i < currentIdx) cls += " completed";
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
