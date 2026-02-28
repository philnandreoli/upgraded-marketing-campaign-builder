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
        <div style={{ marginBottom: "0.75rem" }}>
          <h3>Value Proposition</h3>
          <p style={{ fontSize: "0.9rem" }}>{data.value_proposition}</p>
        </div>
      )}

      {data.positioning && (
        <div style={{ marginBottom: "0.75rem" }}>
          <h3>Positioning</h3>
          <p style={{ fontSize: "0.9rem" }}>{data.positioning}</p>
        </div>
      )}

      {data.objectives?.length > 0 && (
        <div style={{ marginBottom: "0.75rem" }}>
          <h3>Objectives</h3>
          <ul style={{ marginLeft: "1.25rem" }}>
            {data.objectives.map((o, i) => (
              <li key={i} style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>
                {o}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.key_messages?.length > 0 && (
        <div style={{ marginBottom: "0.75rem" }}>
          <h3>Key Messages</h3>
          <ul style={{ marginLeft: "1.25rem" }}>
            {data.key_messages.map((m, i) => (
              <li key={i} style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>
                {m}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(audience.demographics || audience.psychographics) && (
        <div style={{ marginBottom: "0.75rem" }}>
          <h3>Target Audience</h3>
          {audience.demographics && (
            <p style={{ fontSize: "0.85rem" }}>
              <strong>Demographics:</strong> {audience.demographics}
            </p>
          )}
          {audience.psychographics && (
            <p style={{ fontSize: "0.85rem" }}>
              <strong>Psychographics:</strong> {audience.psychographics}
            </p>
          )}
          {audience.pain_points?.length > 0 && (
            <>
              <strong style={{ fontSize: "0.85rem" }}>Pain Points:</strong>
              <ul style={{ marginLeft: "1.25rem" }}>
                {audience.pain_points.map((p, i) => (
                  <li key={i} style={{ fontSize: "0.85rem" }}>{p}</li>
                ))}
              </ul>
            </>
          )}
          {audience.personas?.length > 0 && (
            <>
              <strong style={{ fontSize: "0.85rem" }}>Personas:</strong>
              <ul style={{ marginLeft: "1.25rem" }}>
                {audience.personas.map((p, i) => (
                  <li key={i} style={{ fontSize: "0.85rem" }}>{p}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {data.competitive_landscape && (
        <div>
          <h3>Competitive Landscape</h3>
          <p style={{ fontSize: "0.85rem" }}>{data.competitive_landscape}</p>
        </div>
      )}
    </div>
  );
}
