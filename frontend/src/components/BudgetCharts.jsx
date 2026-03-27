function formatCurrency(amount, currency = "USD") {
  return Number(amount).toLocaleString(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
}

export default function BudgetCharts({ summary }) {
  if (!summary) return null;

  const planned = Number(summary.planned_total);
  const actual = Number(summary.actual_total);
  const maxVal = Math.max(planned, actual, 1);
  const spentRatio = summary.spent_ratio;
  const variance = Number(summary.variance);

  const plannedPct = (planned / maxVal) * 100;
  const actualPct = (actual / maxVal) * 100;
  const utilizationPct = Math.min(spentRatio * 100, 100);
  const overBudget = spentRatio > 1;

  return (
    <div className="card budget-charts">
      <h3>Budget Overview</h3>

      <div className="budget-summary-stats">
        <div className="budget-stat">
          <span className="budget-stat-label">Planned</span>
          <span className="budget-stat-value">{formatCurrency(planned, summary.currency)}</span>
        </div>
        <div className="budget-stat">
          <span className="budget-stat-label">Actual</span>
          <span className="budget-stat-value">{formatCurrency(actual, summary.currency)}</span>
        </div>
        <div className="budget-stat">
          <span className="budget-stat-label">Variance</span>
          <span className={`budget-stat-value ${variance < 0 ? "budget-stat-danger" : "budget-stat-success"}`}>
            {formatCurrency(variance, summary.currency)}
          </span>
        </div>
      </div>

      {/* Planned vs Actual bar chart */}
      <div className="budget-bar-chart" role="img" aria-label="Planned vs actual budget bar chart">
        <div className="budget-bar-row">
          <span className="budget-bar-label">Planned</span>
          <div className="budget-bar-track">
            <div
              className="budget-bar budget-bar--planned"
              style={{ width: `${plannedPct}%` }}
              data-testid="budget-bar-planned"
            />
          </div>
          <span className="budget-bar-value">{formatCurrency(planned, summary.currency)}</span>
        </div>
        <div className="budget-bar-row">
          <span className="budget-bar-label">Actual</span>
          <div className="budget-bar-track">
            <div
              className={`budget-bar budget-bar--actual${overBudget ? " budget-bar--over" : ""}`}
              style={{ width: `${actualPct}%` }}
              data-testid="budget-bar-actual"
            />
          </div>
          <span className="budget-bar-value">{formatCurrency(actual, summary.currency)}</span>
        </div>
      </div>

      {/* Utilization progress bar */}
      <div className="budget-utilization">
        <div className="budget-utilization-header">
          <span className="budget-utilization-label">Budget Utilization</span>
          <span className="budget-utilization-pct">{Math.round(spentRatio * 100)}%</span>
        </div>
        <div className="budget-progress-track" role="progressbar" aria-valuenow={Math.round(spentRatio * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Budget utilization">
          <div
            className={`budget-progress-fill${overBudget ? " budget-progress-fill--over" : spentRatio > summary.alert_threshold_pct ? " budget-progress-fill--warning" : ""}`}
            style={{ width: `${utilizationPct}%` }}
            data-testid="budget-progress-fill"
          />
        </div>
      </div>
    </div>
  );
}
