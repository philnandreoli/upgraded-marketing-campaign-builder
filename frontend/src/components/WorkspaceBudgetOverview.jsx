import { useCallback, useEffect, useState } from "react";
import { getWorkspaceBudgetOverview } from "../api";

function formatCurrency(amount, currency = "USD") {
  return Number(amount).toLocaleString(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
}

function budgetStatus(spentRatio) {
  if (spentRatio > 1) return { label: "Over", cls: "budget-row-over" };
  if (spentRatio >= 0.85) return { label: "Near", cls: "budget-row-near" };
  return { label: "Under", cls: "budget-row-under" };
}

export default function WorkspaceBudgetOverview({ workspaceId }) {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collapsed, setCollapsed] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const data = await getWorkspaceBudgetOverview(workspaceId);
      setOverview(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return null;
  if (error) return null;
  if (!overview || overview.campaign_count === 0) return null;

  const spentPct = Math.round(overview.spent_ratio * 100);
  const variance = Number(overview.variance);

  return (
    <div className="card workspace-budget-overview" data-testid="workspace-budget-overview">
      <button
        type="button"
        className="workspace-budget-toggle"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
      >
        <h3>💰 Budget Overview</h3>
        <svg
          width="18"
          height="18"
          viewBox="0 0 18 18"
          fill="none"
          className={`workspace-budget-chevron${collapsed ? " workspace-budget-chevron--collapsed" : ""}`}
        >
          <path d="M5 7l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {!collapsed && (
        <>
          <div className="budget-summary-stats">
            <div className="budget-stat">
              <span className="budget-stat-label">Total Planned</span>
              <span className="budget-stat-value">{formatCurrency(overview.planned_total, overview.currency)}</span>
            </div>
            <div className="budget-stat">
              <span className="budget-stat-label">Total Actual</span>
              <span className="budget-stat-value">{formatCurrency(overview.actual_total, overview.currency)}</span>
            </div>
            <div className="budget-stat">
              <span className="budget-stat-label">Variance</span>
              <span className={`budget-stat-value ${variance > 0 ? "budget-stat-danger" : "budget-stat-success"}`}>
                {formatCurrency(variance, overview.currency)}
              </span>
            </div>
            <div className="budget-stat">
              <span className="budget-stat-label">Utilization</span>
              <span className="budget-stat-value">{spentPct}%</span>
            </div>
          </div>

          {overview.items.length > 0 && (
            <div className="workspace-budget-campaigns">
              <h4>Per-Campaign Breakdown</h4>
              <div className="workspace-budget-list">
                {overview.items.map((item) => {
                  const planned = Number(item.summary.planned_total);
                  const actual = Number(item.summary.actual_total);
                  const hasEntries = planned > 0 || actual > 0;
                  const itemSpent = Math.round(item.summary.spent_ratio * 100);
                  const status = hasEntries ? budgetStatus(item.summary.spent_ratio) : null;
                  return (
                    <div key={item.campaign_id} className={`workspace-budget-row${status ? ` ${status.cls}` : ""}`}>
                      <div className="workspace-budget-row-name">{item.campaign_name}</div>
                      <div className="workspace-budget-row-nums">
                        <span className="workspace-budget-row-spend">
                          {formatCurrency(actual, item.summary.currency)}
                          <span className="workspace-budget-row-of">
                            {" / "}{formatCurrency(planned, item.summary.currency)}
                          </span>
                        </span>
                        {hasEntries && (
                          <span className={`budget-status-badge budget-status-badge--${status.label.toLowerCase()}`}>
                            {itemSpent}% · {status.label}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
