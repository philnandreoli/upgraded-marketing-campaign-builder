import { useCallback, useState } from "react";
import { getRefinementStats } from "../api";

// ---------------------------------------------------------------------------
// RefinementAnalytics — collapsible analytics section
// ---------------------------------------------------------------------------

export default function RefinementAnalytics({ campaignId, workspaceId, isVisible = false }) {
  const [expanded, setExpanded] = useState(false);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchStats = useCallback(async () => {
    if (!workspaceId || !campaignId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getRefinementStats(workspaceId, campaignId);
      setStats(data);
    } catch (err) {
      setError(err.message || "Failed to load refinement stats.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId]);

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    // Lazy fetch on first expand
    if (next && !stats && !loading) {
      fetchStats();
    }
  };

  if (!isVisible) return null;

  const totalRefinements = stats?.total_refinements ?? 0;
  const avgPerPiece = stats?.avg_per_piece ?? 0;
  const reverts = stats?.reverts ?? 0;
  const approvedFromChat = stats?.approved_from_chat ?? 0;
  const instructionTypes = stats?.top_instruction_types ?? [];

  // Find max count for bar scaling
  const maxTypeCount = instructionTypes.length > 0
    ? Math.max(...instructionTypes.map((t) => t.count ?? 0), 1)
    : 1;

  return (
    <div className="refinement-analytics card" data-testid="refinement-analytics">
      <button
        type="button"
        className="refinement-analytics-toggle"
        onClick={handleToggle}
        aria-expanded={expanded}
      >
        <span className="refinement-analytics-toggle-icon" aria-hidden="true">
          {expanded ? "▾" : "▸"}
        </span>
        <span>📊 Refinement Analytics</span>
      </button>

      {expanded && (
        <div className="refinement-analytics-body">
          {loading && (
            <div className="refinement-analytics-loading">
              <span className="spinner" /> Loading stats…
            </div>
          )}

          {!loading && error && (
            <div className="refinement-analytics-error" role="alert">⚠ {error}</div>
          )}

          {!loading && !error && !stats && (
            <div className="refinement-analytics-empty">No refinement data available.</div>
          )}

          {!loading && !error && stats && (
            <>
              {/* Summary cards */}
              <div className="refinement-analytics-cards">
                <div className="refinement-analytics-stat">
                  <span className="refinement-analytics-stat-value">{totalRefinements}</span>
                  <span className="refinement-analytics-stat-label">Total Refinements</span>
                </div>
                <div className="refinement-analytics-stat">
                  <span className="refinement-analytics-stat-value">{avgPerPiece.toFixed(1)}</span>
                  <span className="refinement-analytics-stat-label">Avg per Piece</span>
                </div>
                <div className="refinement-analytics-stat">
                  <span className="refinement-analytics-stat-value">{reverts}</span>
                  <span className="refinement-analytics-stat-label">Reverts</span>
                </div>
                <div className="refinement-analytics-stat">
                  <span className="refinement-analytics-stat-value">{approvedFromChat}</span>
                  <span className="refinement-analytics-stat-label">Approved from Chat</span>
                </div>
              </div>

              {/* Top instruction types bar chart */}
              {instructionTypes.length > 0 && (
                <div className="refinement-analytics-chart">
                  <h4 className="refinement-analytics-chart-title">Top Instruction Types</h4>
                  {instructionTypes.map((item, idx) => (
                    <div key={idx} className="refinement-analytics-bar-row">
                      <span className="refinement-analytics-bar-label">
                        {item.type || item.label || `Type ${idx + 1}`}
                      </span>
                      <div className="refinement-analytics-bar-track">
                        <div
                          className="refinement-analytics-bar-fill"
                          style={{ width: `${((item.count ?? 0) / maxTypeCount) * 100}%` }}
                          role="progressbar"
                          aria-valuenow={item.count ?? 0}
                          aria-valuemin={0}
                          aria-valuemax={maxTypeCount}
                        />
                      </div>
                      <span className="refinement-analytics-bar-count">{item.count ?? 0}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
