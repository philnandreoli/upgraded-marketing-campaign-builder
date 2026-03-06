/** Format a dollar amount given total budget, channel %, and platform % */
function platformBudget(totalBudget, channelPct, platformPct, currency) {
  if (!totalBudget || totalBudget <= 0) return null;
  const amount = (totalBudget * channelPct / 100) * (platformPct / 100);
  return `${currency || "USD"} ${amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

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
            <div key={i}>
              <div className="channel-bar">
                <span className="bar-label">{rec.channel.replace(/_/g, " ")}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ width: `${Math.min(rec.budget_pct, 100)}%` }}
                  />
                </div>
                <span className="bar-value">{rec.budget_pct}%</span>
              </div>
              {rec.platform_breakdown?.length > 0 && (
                <div style={{ marginLeft: "1rem", marginBottom: "0.25rem" }}>
                  {rec.platform_breakdown.map((pb, j) => {
                    const dollarAmt = platformBudget(data.total_budget, rec.budget_pct, pb.budget_pct, data.currency);
                    return (
                      <div key={j} className="channel-bar" style={{ marginTop: "0.2rem" }}>
                        <span className="bar-label" style={{ fontSize: "0.78rem", textTransform: "capitalize", color: "var(--color-text-muted)" }}>
                          ↳ {pb.platform}
                        </span>
                        <div className="bar-track" style={{ height: "0.5rem" }}>
                          <div
                            className="bar-fill"
                            style={{ width: `${Math.min(pb.budget_pct, 100)}%`, opacity: 0.75 }}
                          />
                        </div>
                        <span className="bar-value" style={{ fontSize: "0.78rem", color: "var(--color-text-muted)" }}>
                          {pb.budget_pct}%{dollarAmt ? ` · ${dollarAmt}` : ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
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
          {rec.platform_breakdown?.length > 0 && (
            <div style={{ marginTop: "0.5rem" }}>
              {rec.platform_breakdown.map((pb, j) => (
                <div key={j} style={{ marginBottom: "0.5rem", paddingLeft: "0.5rem", borderLeft: "2px solid var(--color-border-subtle, var(--color-border))" }}>
                  <strong style={{ fontSize: "0.8rem", textTransform: "capitalize" }}>
                    {pb.platform}
                    {data.total_budget > 0 && (
                      <span style={{ fontWeight: "normal", color: "var(--color-text-muted)", marginLeft: "0.4rem" }}>
                        ({pb.budget_pct}% · {platformBudget(data.total_budget, rec.budget_pct, pb.budget_pct, data.currency)})
                      </span>
                    )}
                  </strong>
                  {pb.timing && (
                    <p style={{ fontSize: "0.78rem", color: "var(--color-text-dim)" }}>
                      ⏰ {pb.timing}
                    </p>
                  )}
                  {pb.tactics?.length > 0 && (
                    <ul style={{ marginLeft: "1.25rem" }}>
                      {pb.tactics.map((t, k) => (
                        <li key={k} style={{ fontSize: "0.78rem", color: "var(--color-text-muted)" }}>
                          {t}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
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
