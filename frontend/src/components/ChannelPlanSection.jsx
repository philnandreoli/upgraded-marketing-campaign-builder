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
        <p className="channel-budget">
          <strong>Total Budget:</strong> {data.currency || "USD"}{" "}
          {data.total_budget.toLocaleString()}
        </p>
      )}

      {data.recommendations?.length > 0 && (
        <div className="channel-bars-container">
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
                <div className="channel-platform-bars">
                  {rec.platform_breakdown.map((pb, j) => {
                    const dollarAmt = platformBudget(data.total_budget, rec.budget_pct, pb.budget_pct, data.currency);
                    return (
                      <div key={j} className="channel-bar channel-bar--platform">
                        <span className="bar-label">
                          ↳ {pb.platform}
                        </span>
                        <div className="bar-track">
                          <div
                            className="bar-fill"
                            style={{ width: `${Math.min(pb.budget_pct, 100)}%` }}
                          />
                        </div>
                        <span className="bar-value">
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
        <div key={i} className="channel-rationale">
          <strong className="channel-name">
            {rec.channel.replace(/_/g, " ")}
          </strong>
          {rec.rationale && (
            <p className="channel-rationale-text">
              {rec.rationale}
            </p>
          )}
          {rec.timing && (
            <p className="channel-timing">
              ⏰ {rec.timing}
            </p>
          )}
          {rec.tactics?.length > 0 && (
            <ul className="channel-tactics">
              {rec.tactics.map((t, j) => (
                <li key={j} className="channel-tactic">
                  {t}
                </li>
              ))}
            </ul>
          )}
          {rec.platform_breakdown?.length > 0 && (
            <div className="channel-platform-breakdown">
              {rec.platform_breakdown.map((pb, j) => (
                <div key={j} className="channel-platform-item">
                  <strong className="channel-platform-name">
                    {pb.platform}
                    {data.total_budget > 0 && (
                      <span className="channel-platform-budget">
                        ({pb.budget_pct}% · {platformBudget(data.total_budget, rec.budget_pct, pb.budget_pct, data.currency)})
                      </span>
                    )}
                  </strong>
                  {pb.timing && (
                    <p className="channel-platform-timing">
                      ⏰ {pb.timing}
                    </p>
                  )}
                  {pb.tactics?.length > 0 && (
                    <ul className="channel-platform-tactics">
                      {pb.tactics.map((t, k) => (
                        <li key={k} className="channel-platform-tactic">
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
        <div className="channel-timeline">
          <h3>Timeline</h3>
          <p className="channel-timeline-text">{data.timeline_summary}</p>
        </div>
      )}
    </div>
  );
}
