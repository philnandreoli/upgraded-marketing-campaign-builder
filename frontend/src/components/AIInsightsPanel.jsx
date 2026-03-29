import { useState, useCallback } from "react";
import { getExperimentInsights } from "../api";

/**
 * AIInsightsPanel — displays AI-generated insights for an experiment.
 *
 * Sections: summary, key findings, recommendations.
 * Includes a refresh button and loading/error states.
 */

export default function AIInsightsPanel({ workspaceId, campaignId, experimentId }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [fetched, setFetched] = useState(false);

  const fetchInsights = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getExperimentInsights(workspaceId, campaignId, experimentId);
      setInsights(data);
      setFetched(true);
    } catch (err) {
      setError(err.message || "Failed to load insights.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId, experimentId]);

  return (
    <div className="card">
      <div className="section-header-row" style={{ marginBottom: "1rem" }}>
        <h3>🤖 AI Insights</h3>
        <button
          type="button"
          className="btn btn-outline"
          style={{ fontSize: "0.8rem" }}
          disabled={loading}
          onClick={fetchInsights}
        >
          {loading ? "Generating…" : fetched ? "🔄 Refresh" : "✨ Generate Insights"}
        </button>
      </div>

      {loading && (
        <div className="loading" style={{ padding: "2rem 0" }}>
          <span className="spinner" /> Generating AI insights…
        </div>
      )}

      {error && (
        <div style={{ color: "var(--color-danger)", padding: "0.75rem 0" }}>
          <p>⚠️ {error}</p>
        </div>
      )}

      {!loading && !error && !fetched && (
        <div style={{ textAlign: "center", padding: "2rem", color: "var(--color-text-muted)" }}>
          <p style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>🤖</p>
          <p>Click "Generate Insights" to get AI-powered analysis of your experiment results.</p>
        </div>
      )}

      {!loading && insights && (
        <div className="exp-insights-body">
          {/* Summary */}
          {(insights.summary || insights.overview) && (
            <div className="exp-insight-section">
              <h4 className="exp-insight-heading">📋 Summary</h4>
              <p className="exp-insight-text">{insights.summary || insights.overview}</p>
            </div>
          )}

          {/* Key Findings */}
          {insights.key_findings && insights.key_findings.length > 0 && (
            <div className="exp-insight-section">
              <h4 className="exp-insight-heading">🔑 Key Findings</h4>
              <ul className="exp-insight-list">
                {insights.key_findings.map((finding, i) => (
                  <li key={i} className="exp-insight-list-item">
                    {typeof finding === "string" ? finding : finding.text || finding.finding || JSON.stringify(finding)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recommendations */}
          {insights.recommendations && insights.recommendations.length > 0 && (
            <div className="exp-insight-section">
              <h4 className="exp-insight-heading">💡 Recommendations</h4>
              <ul className="exp-insight-list">
                {insights.recommendations.map((rec, i) => (
                  <li key={i} className="exp-insight-list-item">
                    {typeof rec === "string" ? rec : rec.text || rec.recommendation || JSON.stringify(rec)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Raw insights text fallback */}
          {!insights.summary && !insights.overview && !insights.key_findings && !insights.recommendations && (
            <div className="exp-insight-section">
              <p className="exp-insight-text" style={{ whiteSpace: "pre-wrap" }}>
                {typeof insights === "string" ? insights : JSON.stringify(insights, null, 2)}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
