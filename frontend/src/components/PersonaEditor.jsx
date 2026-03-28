import { useEffect, useState } from "react";

/**
 * PersonaEditor — modal dialog for creating or editing a persona using
 * structured fields (demographics, psychographics, pain points, behaviors,
 * channels).
 *
 * Props:
 *   open        {boolean}   Whether the modal is visible
 *   onClose     {Function}  Called when the user cancels / closes the modal
 *   onSubmit    {Function}  Called with { name, description } on save, where
 *                           description is formatted from the structured fields
 *   onBack      {Function}  Optional — if provided, shows a "← Back" button
 *   initial     {{ name?, demographics?, psychographics?, pain_points?,
 *                  behaviors?, channels? }}  Pre-fill values
 *   loading     {boolean}   Disables the submit button while saving
 *   title       {string}    Modal title
 *   error       {string|null}  Error message to display
 */
export default function PersonaEditor({
  open,
  onClose,
  onSubmit,
  onBack,
  initial = {},
  loading = false,
  title = "Create Persona",
  error = null,
}) {
  if (!open) return null;

  return (
    <PersonaEditorInner
      key={JSON.stringify(initial)}
      onClose={onClose}
      onSubmit={onSubmit}
      onBack={onBack}
      initial={initial}
      loading={loading}
      title={title}
      error={error}
    />
  );
}

function PersonaEditorInner({ onClose, onSubmit, onBack, initial, loading, title, error }) {
  const [name, setName] = useState(initial.name ?? "");
  const [demographics, setDemographics] = useState(initial.demographics ?? "");
  const [psychographics, setPsychographics] = useState(initial.psychographics ?? "");
  const [painPoints, setPainPoints] = useState(initial.pain_points ?? "");
  const [behaviors, setBehaviors] = useState(initial.behaviors ?? "");
  const [channels, setChannels] = useState(initial.channels ?? "");

  // Close on Escape key
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const canSubmit = name.trim().length > 0 && !loading;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;

    // Format structured fields into a description string
    const parts = [];
    if (demographics.trim()) parts.push(`Demographics: ${demographics.trim()}`);
    if (psychographics.trim()) parts.push(`Psychographics: ${psychographics.trim()}`);
    if (painPoints.trim()) parts.push(`Pain Points: ${painPoints.trim()}`);
    if (behaviors.trim()) parts.push(`Behaviors: ${behaviors.trim()}`);
    if (channels.trim()) parts.push(`Channels: ${channels.trim()}`);

    // Use name as minimal fallback when no structured fields are provided
    const description = parts.join("\n\n") || name.trim();
    onSubmit({ name: name.trim(), description });
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-dialog card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="modal-title">{title}</h3>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="pe-name">Name *</label>
            <input
              id="pe-name"
              required
              maxLength={200}
              placeholder="e.g. Tech-Savvy Millennial"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="pe-demographics">Demographics</label>
            <textarea
              id="pe-demographics"
              maxLength={1000}
              rows={2}
              placeholder="Age range, gender, location, income, education…"
              value={demographics}
              onChange={(e) => setDemographics(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="pe-psychographics">Psychographics</label>
            <textarea
              id="pe-psychographics"
              maxLength={1000}
              rows={2}
              placeholder="Values, interests, lifestyle, personality…"
              value={psychographics}
              onChange={(e) => setPsychographics(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="pe-pain-points">Pain Points</label>
            <textarea
              id="pe-pain-points"
              maxLength={1000}
              rows={2}
              placeholder="Key challenges, frustrations, problems…"
              value={painPoints}
              onChange={(e) => setPainPoints(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="pe-behaviors">Behaviors</label>
            <textarea
              id="pe-behaviors"
              maxLength={1000}
              rows={2}
              placeholder="Purchasing patterns, media consumption, brand interactions…"
              value={behaviors}
              onChange={(e) => setBehaviors(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="pe-channels">Channels</label>
            <textarea
              id="pe-channels"
              maxLength={1000}
              rows={2}
              placeholder="Preferred communication and marketing channels…"
              value={channels}
              onChange={(e) => setChannels(e.target.value)}
            />
          </div>

          {error && (
            <p style={{ color: "var(--color-danger)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              {error}
            </p>
          )}

          <div className="modal-actions">
            {onBack ? (
              <button type="button" className="btn btn-outline" onClick={onBack} disabled={loading}>
                ← Back
              </button>
            ) : (
              <button type="button" className="btn btn-outline" onClick={onClose} disabled={loading}>
                Cancel
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
              {loading ? <><span className="spinner" /> Saving…</> : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


