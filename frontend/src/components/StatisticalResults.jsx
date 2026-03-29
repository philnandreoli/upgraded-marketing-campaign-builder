/**
 * StatisticalResults — displays the statistical analysis results for an experiment.
 *
 * Shows:
 *   - Winner banner (green with crown) when a winner has been selected
 *   - Confidence level
 *   - Probability to beat control (Bayesian)
 *   - Lift percentage
 *   - Sample sizes per variant
 *   - Significance badge
 */

function formatPercent(n) {
  if (n == null) return "—";
  return `${(Number(n) * 100).toFixed(1)}%`;
}

function formatNumber(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString();
}

export default function StatisticalResults({ report, experiment }) {
  if (!report) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
        <p style={{ color: "var(--color-text-muted)" }}>No statistical results available yet. Record metrics to generate a report.</p>
      </div>
    );
  }

  const winner = experiment?.winner || report?.winner;
  const isSignificant = report?.is_significant ?? false;
  const confidence = report?.confidence_level;
  const pValue = report?.p_value;
  const variants = report?.variant_results ? Object.entries(report.variant_results) : [];

  return (
    <div className="exp-stats">
      {/* Winner Banner */}
      {winner && (
        <div className="exp-winner-banner">
          <span className="exp-winner-crown" aria-hidden="true">👑</span>
          <div className="exp-winner-text">
            <strong>Variant {winner}</strong> is the winner!
          </div>
          {experiment?.status === "concluded" && (
            <span className="badge" style={{ background: "rgba(16,185,129,0.2)", color: "var(--color-success)" }}>
              Concluded
            </span>
          )}
        </div>
      )}

      {/* Significance Badge */}
      <div className="card">
        <h3 style={{ marginBottom: "1rem" }}>📐 Statistical Analysis</h3>

        <div className="exp-stats-grid">
          <div className="exp-stat-card">
            <span className="exp-stat-label">Significance</span>
            <span className={`exp-stat-badge ${isSignificant ? "exp-stat-badge--success" : "exp-stat-badge--neutral"}`}>
              {isSignificant ? "✓ Significant" : "Not Significant"}
            </span>
          </div>

          {confidence != null && (
            <div className="exp-stat-card">
              <span className="exp-stat-label">Confidence Level</span>
              <span className="exp-stat-value">{formatPercent(confidence)}</span>
            </div>
          )}

          {pValue != null && (
            <div className="exp-stat-card">
              <span className="exp-stat-label">p-value</span>
              <span className="exp-stat-value">{Number(pValue).toFixed(4)}</span>
            </div>
          )}

          {report?.probability_b_beats_a != null && (
            <div className="exp-stat-card">
              <span className="exp-stat-label">P(B beats A)</span>
              <span className="exp-stat-value">{formatPercent(report.probability_b_beats_a)}</span>
            </div>
          )}

          {report?.lift != null && (
            <div className="exp-stat-card">
              <span className="exp-stat-label">Lift</span>
              <span className={`exp-stat-value ${Number(report.lift) > 0 ? "exp-stat-value--positive" : Number(report.lift) < 0 ? "exp-stat-value--negative" : ""}`}>
                {Number(report.lift) > 0 ? "+" : ""}{formatPercent(report.lift)}
              </span>
            </div>
          )}

          {report?.method && (
            <div className="exp-stat-card">
              <span className="exp-stat-label">Method</span>
              <span className="exp-stat-value" style={{ textTransform: "capitalize" }}>{report.method}</span>
            </div>
          )}
        </div>

        {/* Per-variant breakdown */}
        {variants.length > 0 && (
          <div style={{ marginTop: "1.25rem" }}>
            <h4 style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: "0.5rem" }}>
              Per-Variant Summary
            </h4>
            <table className="exp-stats-table">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th>Impressions</th>
                  <th>Clicks</th>
                  <th>Conversions</th>
                  <th>CTR</th>
                  <th>Conv. Rate</th>
                  <th>Revenue</th>
                </tr>
              </thead>
              <tbody>
                {variants.map(([key, data]) => (
                  <tr key={key} className={key === winner ? "exp-stats-winner-row" : ""}>
                    <td>
                      <span style={{ fontWeight: 600 }}>{key}</span>
                      {key === winner && <span style={{ marginLeft: "0.35rem" }}>👑</span>}
                    </td>
                    <td>{formatNumber(data.total_impressions ?? data.impressions)}</td>
                    <td>{formatNumber(data.total_clicks ?? data.clicks)}</td>
                    <td>{formatNumber(data.total_conversions ?? data.conversions)}</td>
                    <td>{formatPercent(data.click_through_rate ?? data.ctr)}</td>
                    <td>{formatPercent(data.conversion_rate)}</td>
                    <td>{data.total_revenue != null ? `$${Number(data.total_revenue).toFixed(2)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
