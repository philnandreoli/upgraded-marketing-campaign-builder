export default function ChannelPlanSection({ data, error }) {
  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <h2>📡 Channel Plan</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Channel planning failed</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <h2>📡 Channel Plan</h2>
        <div className="loading"><span className="spinner" /> Planning channels…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>📡 Channel Plan</h2>

      {data.total_budget > 0 && (
        <p style={{ fontSize: "0.9rem", marginBottom: "0.75rem" }}>
          <strong>Total Budget:</strong> {data.currency || "USD"}{" "}
          {data.total_budget.toLocaleString()}
        </p>
      )}

      {data.recommendations?.length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          {data.recommendations.map((rec, i) => (
            <div key={i} className="channel-bar">
              <span className="bar-label">{rec.channel.replace(/_/g, " ")}</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.min(rec.budget_pct, 100)}%` }}
                />
              </div>
              <span className="bar-value">{rec.budget_pct}%</span>
            </div>
          ))}
        </div>
      )}

      {data.recommendations?.map((rec, i) => (
        <div key={i} style={{ marginBottom: "0.75rem", paddingLeft: "0.5rem", borderLeft: "2px solid var(--color-border)" }}>
          <strong style={{ fontSize: "0.85rem", textTransform: "capitalize" }}>
            {rec.channel.replace(/_/g, " ")}
          </strong>
          {rec.rationale && (
            <p style={{ fontSize: "0.82rem", color: "var(--color-text-muted)" }}>
              {rec.rationale}
            </p>
          )}
          {rec.timing && (
            <p style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
              ⏰ {rec.timing}
            </p>
          )}
          {rec.tactics?.length > 0 && (
            <ul style={{ marginLeft: "1.25rem" }}>
              {rec.tactics.map((t, j) => (
                <li key={j} style={{ fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
                  {t}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {data.timeline_summary && (
        <div style={{ marginTop: "0.5rem" }}>
          <h3>Timeline</h3>
          <p style={{ fontSize: "0.85rem" }}>{data.timeline_summary}</p>
        </div>
      )}
    </div>
  );
}
