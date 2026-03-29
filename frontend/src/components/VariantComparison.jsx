import { useMemo } from "react";

/**
 * VariantComparison — side-by-side content comparison for A/B variants.
 *
 * Groups content pieces by variant_group and shows each variant's content
 * side by side with simple word-level diff highlighting.
 */

const VARIANT_COLORS = {
  A: "var(--color-primary)",
  B: "#8B5CF6",
  C: "#F49D37",
  D: "#EC4899",
};

function variantColor(variant) {
  return VARIANT_COLORS[variant] || "var(--color-text-muted)";
}

/**
 * Simple word-level diff: marks words that differ between two strings.
 * Returns an array of { word, highlighted } for display.
 */
function wordDiff(base, compare) {
  if (!base || !compare) return (compare || "").split(/(\s+)/).map((w) => ({ word: w, highlighted: false }));
  const baseWords = base.split(/(\s+)/);
  const compWords = compare.split(/(\s+)/);
  return compWords.map((word, i) => ({
    word,
    highlighted: i < baseWords.length ? word !== baseWords[i] : true,
  }));
}

function DiffText({ base, text }) {
  const parts = useMemo(() => wordDiff(base, text), [base, text]);
  return (
    <p className="exp-variant-text">
      {parts.map((p, i) => (
        <span key={i} className={p.highlighted ? "exp-diff-highlight" : ""}>
          {p.word}
        </span>
      ))}
    </p>
  );
}

function MetricsSummaryRow({ metrics, variant }) {
  if (!metrics) return null;
  const data = metrics[variant];
  if (!data) return null;
  return (
    <div className="exp-variant-metrics-row">
      {data.impressions != null && (
        <span className="exp-variant-metric">
          <span className="exp-variant-metric-label">Imp</span>
          <span className="exp-variant-metric-value">{Number(data.impressions).toLocaleString()}</span>
        </span>
      )}
      {data.clicks != null && (
        <span className="exp-variant-metric">
          <span className="exp-variant-metric-label">Clicks</span>
          <span className="exp-variant-metric-value">{Number(data.clicks).toLocaleString()}</span>
        </span>
      )}
      {data.conversions != null && (
        <span className="exp-variant-metric">
          <span className="exp-variant-metric-label">Conv</span>
          <span className="exp-variant-metric-value">{Number(data.conversions).toLocaleString()}</span>
        </span>
      )}
      {data.ctr != null && (
        <span className="exp-variant-metric">
          <span className="exp-variant-metric-label">CTR</span>
          <span className="exp-variant-metric-value">{(Number(data.ctr) * 100).toFixed(2)}%</span>
        </span>
      )}
    </div>
  );
}

export default function VariantComparison({ pieces = [], winner, metricsPerVariant }) {
  // Group pieces by variant_group
  const groups = useMemo(() => {
    const map = {};
    for (const piece of pieces) {
      const group = piece.variant_group || "default";
      if (!map[group]) map[group] = {};
      const variant = piece.variant || "A";
      map[group][variant] = piece;
    }
    return map;
  }, [pieces]);

  const groupEntries = Object.entries(groups);
  if (groupEntries.length === 0) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
        <p style={{ color: "var(--color-text-muted)" }}>No variant content available for comparison.</p>
      </div>
    );
  }

  return (
    <div className="exp-variant-comparison">
      {groupEntries.map(([groupName, variantMap]) => {
        const variantKeys = Object.keys(variantMap).sort();
        const baseContent = variantMap[variantKeys[0]]?.content || "";

        return (
          <div key={groupName} className="card exp-variant-group">
            <h4 className="exp-variant-group-title">
              <span className="exp-variant-group-icon" aria-hidden="true">🔀</span>
              {groupName === "default" ? "Content Variant Group" : groupName}
            </h4>

            <div className="exp-variant-cols" style={{ gridTemplateColumns: `repeat(${variantKeys.length}, 1fr)` }}>
              {variantKeys.map((v) => {
                const piece = variantMap[v];
                const isWinner = winner === v;
                return (
                  <div key={v} className={`exp-variant-col${isWinner ? " exp-variant-col--winner" : ""}`}>
                    <div className="exp-variant-col-header">
                      <span className="exp-variant-col-label" style={{ color: variantColor(v) }}>
                        Variant {v}
                      </span>
                      {isWinner && (
                        <span className="exp-winner-badge">👑 Winner</span>
                      )}
                    </div>

                    {piece?.content_type && (
                      <span className="badge" style={{
                        background: "rgba(99,102,241,0.15)",
                        color: "var(--color-primary-hover)",
                        fontSize: "0.68rem",
                        marginBottom: "0.5rem",
                        display: "inline-block",
                      }}>
                        {piece.content_type}
                      </span>
                    )}

                    {v === variantKeys[0] ? (
                      <p className="exp-variant-text">{piece?.content || "—"}</p>
                    ) : (
                      <DiffText base={baseContent} text={piece?.content || "—"} />
                    )}

                    <MetricsSummaryRow metrics={metricsPerVariant} variant={v} />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
