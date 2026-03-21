export default function StrategySection({ data, error }) {
  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <h2>📋 Strategy</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Strategy generation failed</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <h2>📋 Strategy</h2>
        <div className="loading"><span className="spinner" /> Generating strategy…</div>
      </div>
    );
  }

  const audience = data.target_audience || {};

  return (
    <div className="card">
      <h2>📋 Strategy</h2>

      {data.value_proposition && (
        <div className="strategy-section">
          <h3>Value Proposition</h3>
          <p className="strategy-base-text">{data.value_proposition}</p>
        </div>
      )}

      {data.positioning && (
        <div className="strategy-section">
          <h3>Positioning</h3>
          <p className="strategy-base-text">{data.positioning}</p>
        </div>
      )}

      {data.objectives?.length > 0 && (
        <div className="strategy-section">
          <h3>Objectives</h3>
          <ul className="strategy-list">
            {data.objectives.map((o, i) => (
              <li key={i} className="strategy-list-item">
                {o}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.key_messages?.length > 0 && (
        <div className="strategy-section">
          <h3>Key Messages</h3>
          <ul className="strategy-list">
            {data.key_messages.map((m, i) => (
              <li key={i} className="strategy-list-item">
                {m}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(audience.demographics || audience.psychographics) && (
        <div className="strategy-section">
          <h3>Target Audience</h3>
          {audience.demographics && (
            <p className="strategy-sm-text">
              <strong>Demographics:</strong> {audience.demographics}
            </p>
          )}
          {audience.psychographics && (
            <p className="strategy-sm-text">
              <strong>Psychographics:</strong> {audience.psychographics}
            </p>
          )}
          {audience.pain_points?.length > 0 && (
            <>
              <strong className="strategy-sm-text">Pain Points:</strong>
              <ul className="strategy-list">
                {audience.pain_points.map((p, i) => (
                  <li key={i} className="strategy-sm-text">{p}</li>
                ))}
              </ul>
            </>
          )}
          {audience.personas?.length > 0 && (
            <>
              <strong className="strategy-sm-text">Personas:</strong>
              <ul className="strategy-list">
                {audience.personas.map((p, i) => (
                  <li key={i} className="strategy-sm-text">{p}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {data.competitive_landscape && (
        <div>
          <h3>Competitive Landscape</h3>
          <p className="strategy-sm-text">{data.competitive_landscape}</p>
        </div>
      )}
    </div>
  );
}
