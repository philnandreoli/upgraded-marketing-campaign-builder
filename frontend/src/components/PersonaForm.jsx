import { useEffect, useState, useRef } from "react";

/**
 * PersonaForm — modal dialog for creating or editing a persona.
 *
 * Props:
 *   open        {boolean}   Whether the modal is visible
 *   onClose     {Function}  Called when the user cancels / closes the modal
 *   onSubmit    {Function}  Called with { name, description } on save
 *   initial     {{ name?: string, description?: string }}  Pre-fill values for edit mode
 *   loading     {boolean}   Disables the submit button while saving
 *   title       {string}    Modal title (e.g. "Create Persona" or "Edit Persona")
 *   error       {string|null}  Error message to display
 */
export default function PersonaForm({
  open,
  onClose,
  onSubmit,
  initial = {},
  loading = false,
  title = "Create Persona",
  error = null,
}) {
  if (!open) return null;

  return (
    <PersonaFormInner
      key={`${initial.name ?? ""}-${initial.description ?? ""}`}
      onClose={onClose}
      onSubmit={onSubmit}
      initial={initial}
      loading={loading}
      title={title}
      error={error}
    />
  );
}

function PersonaFormInner({ onClose, onSubmit, initial, loading, title, error }) {
  const [name, setName] = useState(initial.name ?? "");
  const [description, setDescription] = useState(initial.description ?? "");
  const nameRef = useRef(null);

  // Close on Escape key
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const canSubmit = name.trim().length > 0 && description.trim().length > 0 && !loading;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({ name: name.trim(), description: description.trim() });
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
            <label htmlFor="persona-name">Name *</label>
            <input
              ref={nameRef}
              id="persona-name"
              required
              maxLength={200}
              placeholder="e.g. Tech-Savvy Millennial"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="persona-description">Description *</label>
            <textarea
              id="persona-description"
              required
              maxLength={4000}
              rows={5}
              placeholder="Describe the persona — demographics, psychographics, pain points…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {error && (
            <p style={{ color: "var(--color-danger)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              {error}
            </p>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-outline" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
              {loading ? <><span className="spinner" /> Saving…</> : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
