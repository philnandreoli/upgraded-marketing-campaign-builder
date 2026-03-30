import { useState } from "react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function scoreColor(value) {
  if (value == null) return "var(--color-text-muted)";
  if (value < 50) return "var(--color-danger)";
  if (value <= 75) return "var(--color-warning)";
  return "var(--color-success)";
}

function scoreTier(value) {
  if (value == null) return "unknown";
  if (value < 50) return "low";
  if (value <= 75) return "mid";
  return "high";
}

const SUB_SCORE_LABELS = {
  readability: "Readability",
  brand_alignment: "Brand Alignment",
  engagement_potential: "Engagement",
  clarity: "Clarity",
  audience_fit: "Audience Fit",
};

// ---------------------------------------------------------------------------
// ContentScoreBadge
// ---------------------------------------------------------------------------

export default function ContentScoreBadge({ score, loading = false }) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <span className="score-badge score-badge--loading" aria-label="Loading score" data-testid="score-badge-loading">
        <span className="score-badge-pulse" />
      </span>
    );
  }

  if (!score || score.overall == null) {
    return null;
  }

  const overall = Math.round(score.overall);
  const tier = scoreTier(overall);
  const color = scoreColor(overall);

  return (
    <span className="score-badge-wrapper" data-testid="score-badge">
      <button
        type="button"
        className={`score-badge score-badge--${tier}`}
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        aria-label={`Quality score: ${overall}. Click to ${expanded ? "collapse" : "expand"} breakdown.`}
        style={{ borderColor: color, color }}
      >
        {overall}
      </button>

      {expanded && (
        <div className="score-badge-dropdown" role="region" aria-label="Score breakdown">
          <div className="score-badge-breakdown">
            {Object.entries(SUB_SCORE_LABELS).map(([key, label]) => {
              const val = score[key];
              if (val == null) return null;
              const rounded = Math.round(val);
              const barColor = scoreColor(rounded);
              return (
                <div key={key} className="score-badge-row">
                  <span className="score-badge-row-label">{label}</span>
                  <div className="score-badge-bar-track">
                    <div
                      className="score-badge-bar-fill"
                      style={{ width: `${Math.min(rounded, 100)}%`, background: barColor }}
                      role="progressbar"
                      aria-valuenow={rounded}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${label}: ${rounded}`}
                    />
                  </div>
                  <span className="score-badge-row-value" style={{ color: barColor }}>{rounded}</span>
                </div>
              );
            })}
          </div>
          {score.reasoning && (
            <p className="score-badge-reasoning">{score.reasoning}</p>
          )}
        </div>
      )}
    </span>
  );
}
