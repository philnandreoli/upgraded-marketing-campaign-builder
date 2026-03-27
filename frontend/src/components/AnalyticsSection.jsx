export default function AnalyticsSection({ data, error, onOpenComments, unresolvedCount = 0 }) {
  const commentButton = onOpenComments ? (
    <button
      className="section-comment-btn"
      onClick={onOpenComments}
      aria-label="Open analytics comments"
      title="Comments on analytics"
    >
      💬
      {unresolvedCount > 0 && (
        <span className="section-comment-count" data-testid="analytics-comment-count">{unresolvedCount}</span>
      )}
    </button>
  ) : null;

  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <div className="section-header-row">
          <h2>📊 Analytics Plan</h2>
          {commentButton}
        </div>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Analytics planning failed</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <div className="section-header-row">
          <h2>📊 Analytics Plan</h2>
          {commentButton}
        </div>
        <div className="loading"><span className="spinner" /> Setting up analytics…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="section-header-row">
        <h2>📊 Analytics Plan</h2>
        {commentButton}
      </div>

      <div className="analytics-meta">
        {data.reporting_cadence && (
          <span>
            <strong>Reporting:</strong> {data.reporting_cadence}
          </span>
        )}
        {data.attribution_model && (
          <span>
            <strong>Attribution:</strong> {data.attribution_model}
          </span>
        )}
      </div>

      {data.kpis?.length > 0 && (
        <>
          <h3>Key Performance Indicators</h3>
          <div className="kpi-grid">
            {data.kpis.map((kpi, i) => (
              <div key={i} className="kpi-card">
                <div className="kpi-name">{kpi.name}</div>
                {kpi.target_value && (
                  <div className="kpi-target">🎯 Target: {kpi.target_value}</div>
                )}
                {kpi.measurement_method && (
                  <div className="kpi-method">📐 {kpi.measurement_method}</div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {data.tracking_tools?.length > 0 && (
        <div className="analytics-tools">
          <h3>Tracking Tools</h3>
          <p className="analytics-text">{data.tracking_tools.join(", ")}</p>
        </div>
      )}

      {data.success_criteria && (
        <div className="analytics-criteria">
          <h3>Success Criteria</h3>
          <p className="analytics-text">{data.success_criteria}</p>
        </div>
      )}
    </div>
  );
}
