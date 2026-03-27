import { useCallback, useEffect, useState } from "react";
import { getWorkspaceBudgetOverview } from "../api";

function formatCurrency(amount, currency = "USD") {
  return Number(amount).toLocaleString(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
}

export default function WorkspaceBudgetOverview({ workspaceId }) {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
      <h3>💰 Budget Overview</h3>

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
          <span className={`budget-stat-value ${variance < 0 ? "budget-stat-danger" : "budget-stat-success"}`}>
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
          <table className="budget-table">
            <thead>
              <tr>
                <th>Campaign</th>
                <th className="budget-table-amount">Planned</th>
                <th className="budget-table-amount">Actual</th>
                <th className="budget-table-amount">Utilization</th>
              </tr>
            </thead>
            <tbody>
              {overview.items.map((item) => {
                const itemSpent = Math.round(item.summary.spent_ratio * 100);
                const overBudget = item.summary.spent_ratio > 1;
                return (
                  <tr key={item.campaign_id}>
                    <td>{item.campaign_name}</td>
                    <td className="budget-table-amount">
                      {formatCurrency(item.summary.planned_total, item.summary.currency)}
                    </td>
                    <td className="budget-table-amount">
                      {formatCurrency(item.summary.actual_total, item.summary.currency)}
                    </td>
                    <td className={`budget-table-amount ${overBudget ? "budget-stat-danger" : ""}`}>
                      {itemSpent}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
