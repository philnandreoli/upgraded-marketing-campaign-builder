import { useState } from "react";
import PersonaForm from "./PersonaForm";

export default function StrategySection({ data, error, onOpenComments, unresolvedCount = 0, workspaceId: _workspaceId, onSavePersona, canSavePersona = false }) {
  const [personaFormOpen, setPersonaFormOpen] = useState(false);
  const [personaFormLoading, setPersonaFormLoading] = useState(false);
  const [personaFormError, setPersonaFormError] = useState(null);
  const [savedMessage, setSavedMessage] = useState(null);

  const audience = data?.target_audience || {};

  // Build a prefill description from audience insights
  const buildPersonaDescription = () => {
    const parts = [];
    if (audience.demographics) parts.push(`Demographics: ${audience.demographics}`);
    if (audience.psychographics) parts.push(`Psychographics: ${audience.psychographics}`);
    if (audience.pain_points?.length > 0) parts.push(`Pain Points: ${audience.pain_points.join("; ")}`);
    if (audience.personas?.length > 0) parts.push(`Personas: ${audience.personas.join("; ")}`);
    return parts.join("\n\n");
  };

  const handleSavePersona = async ({ name, description }) => {
    if (!onSavePersona) return;
    setPersonaFormLoading(true);
    setPersonaFormError(null);
    try {
      await onSavePersona({ name, description });
      setPersonaFormOpen(false);
      setSavedMessage(`Persona "${name}" saved!`);
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err) {
      setPersonaFormError(err.message || "Failed to save persona.");
    } finally {
      setPersonaFormLoading(false);
    }
  };

  const commentButton = onOpenComments ? (
    <button
      className="section-comment-btn"
      onClick={onOpenComments}
      aria-label="Open strategy comments"
      title="Comments on strategy"
    >
      💬
      {unresolvedCount > 0 && (
        <span className="section-comment-count" data-testid="strategy-comment-count">{unresolvedCount}</span>
      )}
    </button>
  ) : null;

  if (!data && error) {
    return (
      <div className="card stage-error-card">
        <div className="section-header-row">
          <h2>📋 Strategy</h2>
          {commentButton}
        </div>
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
        <div className="section-header-row">
          <h2>📋 Strategy</h2>
          {commentButton}
        </div>
        <div className="loading"><span className="spinner" /> Generating strategy…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="section-header-row">
        <h2>📋 Strategy</h2>
        {commentButton}
      </div>

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
          {canSavePersona && (
            <button
              type="button"
              className="btn btn-outline"
              style={{ marginTop: "0.75rem", fontSize: "0.82rem" }}
              onClick={() => {
                setPersonaFormError(null);
                setPersonaFormOpen(true);
              }}
            >
              👤 Save as Persona
            </button>
          )}
          {savedMessage && (
            <p style={{ color: "var(--color-success, #22c55e)", fontSize: "0.82rem", marginTop: "0.5rem" }}>
              ✓ {savedMessage}
            </p>
          )}
        </div>
      )}

      {data.competitive_landscape && (
        <div>
          <h3>Competitive Landscape</h3>
          <p className="strategy-sm-text">{data.competitive_landscape}</p>
        </div>
      )}

      <PersonaForm
        open={personaFormOpen}
        onClose={() => setPersonaFormOpen(false)}
        onSubmit={handleSavePersona}
        initial={{ name: "", description: buildPersonaDescription() }}
        loading={personaFormLoading}
        title="Save as Persona"
        error={personaFormError}
      />
    </div>
  );
}
