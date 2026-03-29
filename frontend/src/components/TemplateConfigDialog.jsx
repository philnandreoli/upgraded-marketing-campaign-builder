import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { markAsTemplate, updateTemplate, ApiError } from "../api";
import { useUser } from "../UserContext";

const CATEGORY_OPTIONS = [
  "Product Launch",
  "Seasonal Promo",
  "Event",
  "Awareness",
  "Lead Generation",
  "Retention",
];

const PARAM_TYPES = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
];

/**
 * TemplateConfigDialog — modal for marking a campaign as a template
 * or editing existing template metadata.
 *
 * Props:
 *   isOpen       boolean
 *   onClose      () => void
 *   campaign     campaign object
 *   workspaceId  string
 *   mode         "create" | "edit"
 *   onSuccess    (result) => void — called after successful save
 */
export default function TemplateConfigDialog({ isOpen, onClose, campaign, workspaceId, mode = "create", onSuccess }) {
  const { isAdmin } = useUser();

  const initialData = mode === "edit" && campaign ? {
    category: campaign.template_category || "",
    tags: campaign.template_tags || [],
    description: campaign.template_description || "",
    visibility: campaign.template_visibility || "workspace",
    parameters: campaign.template_parameters || [],
  } : null;

  const [category, setCategory] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [isCustomCategory, setIsCustomCategory] = useState(false);
  const [tags, setTags] = useState([]);
  const [tagInput, setTagInput] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState("workspace");
  const [parameters, setParameters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const cancelRef = useRef(null);
  const dialogRef = useRef(null);
  const tagInputRef = useRef(null);

  // Reset / populate state when dialog opens
  useEffect(() => {
    if (!isOpen) return;
    if (initialData) {
      const knownCategory = CATEGORY_OPTIONS.includes(initialData.category);
      setCategory(knownCategory ? initialData.category : "__custom__");
      setCustomCategory(knownCategory ? "" : initialData.category);
      setIsCustomCategory(!knownCategory && !!initialData.category);
      setTags([...(initialData.tags || [])]);
      setDescription(initialData.description || "");
      setVisibility(initialData.visibility || "workspace");
      setParameters(
        (initialData.parameters || []).map((p, i) => ({ ...p, _key: `init-${i}` }))
      );
    } else {
      setCategory("");
      setCustomCategory("");
      setIsCustomCategory(false);
      setTags([]);
      setDescription("");
      setVisibility("workspace");
      setParameters([]);
    }
    setTagInput("");
    setLoading(false);
    setError(null);
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-focus cancel button on open
  useEffect(() => {
    if (isOpen && cancelRef.current) {
      cancelRef.current.focus();
    }
  }, [isOpen]);

  // Escape key + focus trap
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (!loading) onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, loading]);

  // --- Tag management ---
  const handleTagKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  };

  const addTag = () => {
    const val = tagInput.trim();
    if (val && !tags.includes(val)) {
      setTags((prev) => [...prev, val]);
    }
    setTagInput("");
    tagInputRef.current?.focus();
  };

  const removeTag = (tag) => {
    setTags((prev) => prev.filter((t) => t !== tag));
  };

  // --- Parameter management ---
  const addParameter = () => {
    setParameters((prev) => [
      ...prev,
      { name: "", type: "text", default: "", description: "", _key: `new-${Date.now()}` },
    ]);
  };

  const updateParameter = (index, field, value) => {
    setParameters((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const removeParameter = (index) => {
    setParameters((prev) => prev.filter((_, i) => i !== index));
  };

  // --- Category ---
  const handleCategoryChange = (value) => {
    if (value === "__custom__") {
      setCategory("__custom__");
      setIsCustomCategory(true);
      setCustomCategory("");
    } else {
      setCategory(value);
      setIsCustomCategory(false);
      setCustomCategory("");
    }
  };

  // --- Submit ---
  const handleSave = async () => {
    if (!campaign) return;
    setLoading(true);
    setError(null);

    const resolvedCategory = isCustomCategory ? customCategory.trim() : category;

    const config = {
      category: resolvedCategory || null,
      tags,
      description: description.trim(),
      visibility,
      parameters: parameters
        .filter((p) => p.name.trim())
        .map(({ _key, ...rest }) => ({
          name: rest.name.trim(),
          type: rest.type,
          default: rest.default || null,
          description: rest.description || "",
        })),
    };

    try {
      let result;
      if (mode === "edit" && campaign.template_id) {
        result = await updateTemplate(campaign.template_id, config);
      } else {
        result = await markAsTemplate(workspaceId, campaign.id, config);
      }
      onSuccess?.(result);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setError("You don't have permission to modify template settings.");
        } else if (err.status === 409) {
          setError("This campaign is already marked as a template.");
        } else {
          setError(err.message || "An unexpected error occurred.");
        }
      } else {
        setError("Network error — please check your connection and try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !campaign) return null;

  return createPortal(
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="template-config-dialog-title">
      <div className="modal-box card template-config-dialog" ref={dialogRef}>
        <div className="modal-header">
          <h2 id="template-config-dialog-title">
            {mode === "edit" ? "Edit Template Settings" : "Save as Template"}
          </h2>
          <p className="clone-dialog-subtitle">
            {mode === "edit"
              ? "Update the template configuration for this campaign."
              : `Mark "${campaign.product_or_service || campaign.brief?.product_or_service || "this campaign"}" as a reusable template.`}
          </p>
        </div>

        {/* Category */}
        <div className="clone-dialog-section">
          <label className="clone-dialog-section-label" htmlFor="template-category">
            Category
          </label>
          <select
            id="template-category"
            className="clone-dialog-select"
            value={isCustomCategory ? "__custom__" : category}
            onChange={(e) => handleCategoryChange(e.target.value)}
            disabled={loading}
          >
            <option value="">Select a category…</option>
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
            <option value="__custom__">Custom…</option>
          </select>
          {isCustomCategory && (
            <input
              type="text"
              className="clone-template-param-input"
              placeholder="Enter custom category"
              value={customCategory}
              onChange={(e) => setCustomCategory(e.target.value)}
              disabled={loading}
              style={{ marginTop: "0.5rem" }}
              aria-label="Custom category name"
            />
          )}
        </div>

        {/* Tags */}
        <div className="clone-dialog-section">
          <label className="clone-dialog-section-label" htmlFor="template-tags-input">
            Tags
          </label>
          <div className="template-tags-wrapper">
            {tags.map((tag) => (
              <span key={tag} className="template-tag-chip">
                {tag}
                <button
                  type="button"
                  className="template-tag-remove"
                  onClick={() => removeTag(tag)}
                  disabled={loading}
                  aria-label={`Remove tag ${tag}`}
                >
                  ×
                </button>
              </span>
            ))}
            <input
              ref={tagInputRef}
              id="template-tags-input"
              type="text"
              className="template-tag-input"
              placeholder="Type and press Enter to add"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
              disabled={loading}
            />
          </div>
        </div>

        {/* Description */}
        <div className="clone-dialog-section">
          <label className="clone-dialog-section-label" htmlFor="template-description">
            Description
          </label>
          <textarea
            id="template-description"
            className="template-description-input"
            placeholder="Describe when and how to use this template…"
            value={description}
            onChange={(e) => setDescription(e.target.value.slice(0, 500))}
            disabled={loading}
            maxLength={500}
            rows={3}
          />
          <span className="template-char-count">{description.length}/500</span>
        </div>

        {/* Visibility */}
        <fieldset className="clone-dialog-section" disabled={loading}>
          <legend className="clone-dialog-section-label">Visibility</legend>
          <div className="template-visibility-options" role="radiogroup" aria-label="Template visibility">
            <label className={`clone-depth-option${visibility === "workspace" ? " clone-depth-option--selected" : ""}`}>
              <input
                type="radio"
                name="template-visibility"
                value="workspace"
                checked={visibility === "workspace"}
                onChange={() => setVisibility("workspace")}
                className="sr-only"
              />
              <span className="clone-depth-option-label">Workspace Only</span>
              <span className="clone-depth-option-desc">Only members of this workspace can use the template.</span>
            </label>
            {isAdmin && (
              <label className={`clone-depth-option${visibility === "organization" ? " clone-depth-option--selected" : ""}`}>
                <input
                  type="radio"
                  name="template-visibility"
                  value="organization"
                  checked={visibility === "organization"}
                  onChange={() => setVisibility("organization")}
                  className="sr-only"
                />
                <span className="clone-depth-option-label">Organization-wide</span>
                <span className="clone-depth-option-desc">All users in the organization can discover and clone this template.</span>
              </label>
            )}
          </div>
        </fieldset>

        {/* Parameters builder */}
        <fieldset className="clone-dialog-section" disabled={loading}>
          <legend className="clone-dialog-section-label">Template Parameters</legend>
          {parameters.length > 0 && (
            <div className="template-params-list">
              {parameters.map((param, idx) => (
                <div key={param._key} className="template-param-row">
                  <input
                    type="text"
                    className="clone-template-param-input"
                    placeholder="Name"
                    value={param.name}
                    onChange={(e) => updateParameter(idx, "name", e.target.value)}
                    aria-label={`Parameter ${idx + 1} name`}
                  />
                  <select
                    className="clone-dialog-select template-param-type-select"
                    value={param.type}
                    onChange={(e) => updateParameter(idx, "type", e.target.value)}
                    aria-label={`Parameter ${idx + 1} type`}
                  >
                    {PARAM_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    className="clone-template-param-input"
                    placeholder="Default (optional)"
                    value={param.default || ""}
                    onChange={(e) => updateParameter(idx, "default", e.target.value)}
                    aria-label={`Parameter ${idx + 1} default value`}
                  />
                  <input
                    type="text"
                    className="clone-template-param-input"
                    placeholder="Description"
                    value={param.description || ""}
                    onChange={(e) => updateParameter(idx, "description", e.target.value)}
                    aria-label={`Parameter ${idx + 1} description`}
                  />
                  <button
                    type="button"
                    className="btn btn-outline template-param-remove"
                    onClick={() => removeParameter(idx)}
                    aria-label={`Remove parameter ${idx + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <button
            type="button"
            className="btn btn-outline"
            onClick={addParameter}
            style={{ marginTop: "0.5rem" }}
          >
            + Add Parameter
          </button>
        </fieldset>

        {/* Error display */}
        {error && (
          <div className="clone-dialog-error" role="alert">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="confirm-dialog-actions">
          <button
            ref={cancelRef}
            type="button"
            className="btn btn-outline"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" aria-hidden="true" /> Saving…
              </>
            ) : mode === "edit" ? (
              "Save Changes"
            ) : (
              "Save as Template"
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
