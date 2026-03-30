import { useState } from "react";
import PersonaForm from "./PersonaForm";
import PersonaEditor from "./PersonaEditor";

export default function StrategySection({ data, error, onOpenComments, unresolvedCount = 0, workspaceId: _workspaceId, onSavePersona, onParsePersona, canSavePersona = false, hasPreselectedPersonas = false }) {
  const [personaPhase, setPersonaPhase] = useState(null); // null | "freeform" | "editor"
  const [personaFormLoading, setPersonaFormLoading] = useState(false);
  const [personaFormError, setPersonaFormError] = useState(null);
  const [savedMessage, setSavedMessage] = useState(null);
  const [personaFormInitial, setPersonaFormInitial] = useState({ name: "", description: "" });
  const [parsedFields, setParsedFields] = useState(null);
  const [savedPersonaIndices, setSavedPersonaIndices] = useState(new Set());
  const [savingPersonaIndex, setSavingPersonaIndex] = useState(null);
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorError, setEditorError] = useState(null);

  const audience = data?.target_audience || {};

  // Extract a short name from a persona string like "Name (Archetype): description..."
  const parsePersonaName = (personaStr) => {
    const colonIdx = personaStr.indexOf(":");
    if (colonIdx > 0 && colonIdx < 80) {
      const raw = personaStr.slice(0, colonIdx).trim();
      const parenIdx = raw.indexOf("(");
      return parenIdx > 0 ? raw.slice(0, parenIdx).trim() : raw;
    }
    return personaStr.split(/\s+/).slice(0, 4).join(" ");
  };

  const openPersonaForm = (personaStr, index) => {
    setPersonaFormError(null);
    setEditorError(null);
    setParsedFields(null);
    setPersonaFormInitial({
      name: parsePersonaName(personaStr),
      description: personaStr,
    });
    setSavingPersonaIndex(index);
    setPersonaPhase("freeform");
  };

  const handleCloseAll = () => {
    setPersonaPhase(null);
    setParsedFields(null);
    setPersonaFormError(null);
    setEditorError(null);
  };

  // "✨ Structure with AI" — parse, then open editor
  const handleStructureWithAI = async ({ name, description }) => {
    if (!onParsePersona) return;
    setPersonaFormLoading(true);
    setPersonaFormError(null);
    try {
      const result = await onParsePersona({ name, description });
      setParsedFields(result);
      setPersonaPhase("editor");
    } catch (err) {
      console.warn("AI persona parse failed:", err);
      setPersonaFormError("AI structuring failed. You can fill the fields manually.");
      setParsedFields({ name, demographics: description, psychographics: "", pain_points: "", behaviors: "", channels: "" });
      setPersonaPhase("editor");
    } finally {
      setPersonaFormLoading(false);
    }
  };

  // Skip AI — open editor directly
  const handleSkipAI = ({ name, description }) => {
    setParsedFields({ name, demographics: description, psychographics: "", pain_points: "", behaviors: "", channels: "" });
    setPersonaFormError(null);
    setPersonaPhase("editor");
  };

  const handleSavePersona = async ({ name, description }) => {
    if (!onSavePersona) return;
    setEditorLoading(true);
    setEditorError(null);
    try {
      await onSavePersona({ name, description });
      handleCloseAll();
      if (savingPersonaIndex != null) {
        setSavedPersonaIndices((prev) => new Set(prev).add(savingPersonaIndex));
      }
      setSavedMessage(`Persona "${name}" saved!`);
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err) {
      setEditorError(err.message || "Failed to save persona.");
    } finally {
      setEditorLoading(false);
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
                  <li key={i} className="strategy-sm-text">
                    <span>{p}</span>
                    {canSavePersona && !hasPreselectedPersonas && !savedPersonaIndices.has(i) && (
                      <div style={{ marginTop: "0.4rem" }}>
                        <button
                          type="button"
                          className="btn btn-outline"
                          style={{ fontSize: "0.78rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => openPersonaForm(p, i)}
                        >
                          👤 Save as Persona
                        </button>
                      </div>
                    )}
                    {savedPersonaIndices.has(i) && (
                      <span style={{ color: "var(--color-success, #22c55e)", fontSize: "0.78rem", marginLeft: "0.5rem" }}>
                        ✓ Saved
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </>
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

      {/* Phase 1: Freeform describe modal */}
      <PersonaForm
        open={personaPhase === "freeform"}
        onClose={handleCloseAll}
        onSubmit={handleStructureWithAI}
        onSkip={handleSkipAI}
        initial={personaFormInitial}
        loading={personaFormLoading}
        title="Save as Persona"
        error={personaFormError}
        submitLabel="✨ Structure with AI"
      />

      {/* Phase 2: Structured editor modal */}
      <PersonaEditor
        open={personaPhase === "editor"}
        onClose={handleCloseAll}
        onBack={() => setPersonaPhase("freeform")}
        onSubmit={handleSavePersona}
        initial={parsedFields ?? {}}
        loading={editorLoading}
        title="Review & Save Persona"
        error={editorError}
      />
    </div>
  );
}
