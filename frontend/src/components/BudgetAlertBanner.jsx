function formatCurrency(amount, currency = "USD") {
  return Number(amount).toLocaleString(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
}

export default function BudgetAlertBanner({ summary }) {
  if (!summary?.is_alert_triggered) return null;

  const spentPct = Math.round(summary.spent_ratio * 100);
  const thresholdPct = Math.round(summary.alert_threshold_pct * 100);
  const overBudget = summary.spent_ratio > 1;

  return (
    <div
      className={`budget-alert-banner${overBudget ? " budget-alert-banner--danger" : " budget-alert-banner--warning"}`}
      role="alert"
      data-testid="budget-alert-banner"
    >
      <span className="budget-alert-icon" aria-hidden="true">
        {overBudget ? "🚨" : "⚠️"}
      </span>
      <div className="budget-alert-content">
        <strong>
          {overBudget
            ? "Budget exceeded!"
            : "Budget threshold reached"}
        </strong>
        <span>
          {overBudget
            ? ` Actual spend (${formatCurrency(summary.actual_total, summary.currency)}) exceeds planned budget (${formatCurrency(summary.planned_total, summary.currency)}) — ${spentPct}% utilized.`
            : ` Spend has reached ${spentPct}% of the planned budget (threshold: ${thresholdPct}%). Actual: ${formatCurrency(summary.actual_total, summary.currency)} of ${formatCurrency(summary.planned_total, summary.currency)}.`}
        </span>
      </div>
    </div>
  );
}
