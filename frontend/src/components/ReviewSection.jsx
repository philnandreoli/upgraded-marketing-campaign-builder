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

  if (!data && status === "review") {
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
          <div className="review-score-container">
            <div>
              <span className="review-score-label">
                Brand Consistency
              </span>
              <div className={`review-score ${scoreClass}`}>
                {data.brand_consistency_score?.toFixed(1)} <span className="review-score-suffix">/ 10</span>
              </div>
            </div>
            <div>
              <span className="review-score-label">
                AI Verdict
              </span>
              <div className={`review-verdict ${data.approved ? "review-verdict--approved" : "review-verdict--needs-review"}`}>
                {data.approved ? "✅ Approved" : "⚠️ Needs Review"}
              </div>
            </div>
          </div>

          {data.issues?.length > 0 && (
            <div className="review-section-block">
              <h3>Issues</h3>
              <ul className="review-issues">
                {data.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}

          {data.suggestions?.length > 0 && (
            <div className="review-section-block">
              <h3>Suggestions</h3>
              <ul className="review-suggestions">
                {data.suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          {data.human_notes && (
            <div className="review-section-block">
              <h3>Human Reviewer Notes</h3>
              <p className="review-text">{data.human_notes}</p>
            </div>
          )}
        </>
      )}

      {/* Review is now read-only — content approval happens in the Content Approval stage */}
      {data && (
        <p className="review-feedback-note">
          Review feedback will be automatically sent to improve the content in the next stage.
        </p>
      )}
    </div>
  );
}
