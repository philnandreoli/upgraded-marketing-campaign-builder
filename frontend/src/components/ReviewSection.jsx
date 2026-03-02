export default function ReviewSection({ data, _campaignId, status, error }) {
  const scoreClass =
    data?.brand_consistency_score >= 7
      ? "high"
      : data?.brand_consistency_score >= 4
        ? "medium"
        : "low";

  if (!data && error && status !== "approved" && status !== "rejected") {
    return (
      <div className="card stage-error-card">
        <h2>🔍 Review &amp; QA</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Review generation failed</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data && status !== "approved" && status !== "rejected") {
    return (
      <div className="card">
        <h2>🔍 Review &amp; QA</h2>
        <div className="loading"><span className="spinner" /> Running review…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>🔍 Review &amp; QA</h2>

      {data && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", marginBottom: "1rem" }}>
            <div>
              <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
                Brand Consistency
              </span>
              <div className={`review-score ${scoreClass}`}>
                {data.brand_consistency_score?.toFixed(1)} <span style={{ fontSize: "0.85rem" }}>/ 10</span>
              </div>
            </div>
            <div>
              <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
                AI Verdict
              </span>
              <div style={{ fontWeight: 600, color: data.approved ? "var(--color-success)" : "var(--color-warning)" }}>
                {data.approved ? "✅ Approved" : "⚠️ Needs Review"}
              </div>
            </div>
          </div>

          {data.issues?.length > 0 && (
            <div style={{ marginBottom: "0.75rem" }}>
              <h3>Issues</h3>
              <ul className="review-issues">
                {data.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}

          {data.suggestions?.length > 0 && (
            <div style={{ marginBottom: "0.75rem" }}>
              <h3>Suggestions</h3>
              <ul className="review-suggestions">
                {data.suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {data.human_notes && (
            <div style={{ marginBottom: "0.75rem" }}>
              <h3>Human Reviewer Notes</h3>
              <p style={{ fontSize: "0.85rem" }}>{data.human_notes}</p>
            </div>
          )}
        </>
      )}

      {/* Review is now read-only — content approval happens in the Content Approval stage */}
      {data && (
        <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginTop: "1rem" }}>
          Review feedback will be automatically sent to improve the content in the next stage.
        </p>
      )}
    </div>
  );
}
