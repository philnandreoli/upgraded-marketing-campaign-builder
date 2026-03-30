import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { cloneCampaign, ApiError } from "../api";
import { useWorkspace } from "../WorkspaceContext";
import FormSelect from "./FormSelect";

const DEPTH_OPTIONS = [
  {
    value: "brief",
    label: "Brief Only",
    description: "Copies the campaign brief (goal, audience, channels, budget). No strategy or content.",
  },
  {
    value: "strategy",
    label: "Brief + Strategy",
    description: "Copies the brief and the generated strategy. Content and channel plan are not included.",
  },
  {
    value: "content",
    label: "Brief + Strategy + Content",
    description: "Copies the brief, strategy, and all content pieces. Channel plan and analytics are excluded.",
  },
  {
    value: "full",
    label: "Full Campaign",
    description: "Copies everything: brief, strategy, content, channel plan, analytics, and review data.",
  },
];

/**
 * CloneDialog — modal for cloning a campaign with configurable depth,
 * target workspace, and template parameter overrides.
 *
 * Props:
 *   isOpen            boolean
 *   onClose           () => void
 *   campaign          campaign object (must include id, workspace_id, is_template, template_parameters)
 *   sourceWorkspaceId string
 */
export default function CloneDialog({ isOpen, onClose, campaign, sourceWorkspaceId }) {
  const navigate = useNavigate();
  const { workspaces } = useWorkspace();

  const [depth, setDepth] = useState("brief");
  const [targetWorkspaceId, setTargetWorkspaceId] = useState(sourceWorkspaceId || "");
  const [parameterOverrides, setParameterOverrides] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const cancelRef = useRef(null);
  const dialogRef = useRef(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (isOpen) {
      setDepth("brief");
      setTargetWorkspaceId(sourceWorkspaceId || "");
      setParameterOverrides({});
      setLoading(false);
      setError(null);
    }
  }, [isOpen, sourceWorkspaceId]);

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

  const isTemplate = campaign?.is_template === true;
  const templateParams = campaign?.template_parameters;
  const hasTemplateParams =
    isTemplate && Array.isArray(templateParams) && templateParams.length > 0;

  const handleParameterChange = (paramName, value) => {
    setParameterOverrides((prev) => ({ ...prev, [paramName]: value }));
  };

  const handleClone = async () => {
    if (!campaign) return;
    setLoading(true);
    setError(null);
    try {
      const overrides =
        hasTemplateParams && Object.keys(parameterOverrides).length > 0
          ? parameterOverrides
          : null;
      const result = await cloneCampaign(sourceWorkspaceId, campaign.id, {
        depth,
        targetWorkspaceId: targetWorkspaceId !== sourceWorkspaceId ? targetWorkspaceId : null,
        parameterOverrides: overrides,
      });
      const newId = result?.id ?? result?.campaign_id;
      const targetWid = targetWorkspaceId || sourceWorkspaceId;
      onClose();
      if (newId) {
        navigate(`/workspaces/${targetWid}/campaigns/${newId}/edit`);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setError("You don't have permission to clone this campaign.");
        } else if (err.status === 409) {
          setError("A clone of this campaign already exists or there is a conflict. Please try again.");
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
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="clone-dialog-title">
      <div className="modal-box card clone-dialog" ref={dialogRef}>
        <div className="modal-header">
          <h2 id="clone-dialog-title">Clone Campaign</h2>
          <p className="clone-dialog-subtitle">
            Create a copy of <strong>{campaign.product_or_service || campaign.brief?.product_or_service || "this campaign"}</strong>
          </p>
        </div>

        {/* Depth selector */}
        <fieldset className="clone-dialog-section" disabled={loading}>
          <legend className="clone-dialog-section-label">Clone Depth</legend>
          <div className="clone-depth-options" role="radiogroup" aria-label="Clone depth">
            {DEPTH_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`clone-depth-option${depth === opt.value ? " clone-depth-option--selected" : ""}`}
              >
                <input
                  type="radio"
                  name="clone-depth"
                  value={opt.value}
                  checked={depth === opt.value}
                  onChange={() => setDepth(opt.value)}
                  className="sr-only"
                />
                <span className="clone-depth-option-label">{opt.label}</span>
                <span className="clone-depth-option-desc">{opt.description}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Target workspace dropdown */}
        <div className="clone-dialog-section">
          <label className="clone-dialog-section-label" htmlFor="clone-target-workspace">
            Target Workspace
          </label>
          <FormSelect
            id="clone-target-workspace"
            options={workspaces.map((ws) => ({
              value: ws.id,
              label: `${ws.name}${ws.id === sourceWorkspaceId ? " (source)" : ""}`,
            }))}
            value={targetWorkspaceId}
            onChange={(val) => setTargetWorkspaceId(val)}
            ariaLabel="Target workspace"
          />
        </div>

        {/* Template parameters */}
        {hasTemplateParams && (
          <fieldset className="clone-dialog-section" disabled={loading}>
            <legend className="clone-dialog-section-label">Template Parameters</legend>
            <div className="clone-template-params">
              {templateParams.map((param) => (
                <div key={param.name} className="clone-template-param">
                  <label
                    className="clone-template-param-label"
                    htmlFor={`param-${param.name}`}
                    title={param.description || ""}
                  >
                    {param.name}
                    {param.description && (
                      <span className="clone-template-param-hint" aria-label={param.description}>
                        {" "}ℹ️
                      </span>
                    )}
                  </label>
                  <input
                    id={`param-${param.name}`}
                    type={param.type === "number" ? "number" : param.type === "date" ? "date" : "text"}
                    className="clone-template-param-input"
                    placeholder={param.default != null ? String(param.default) : ""}
                    value={parameterOverrides[param.name] ?? ""}
                    onChange={(e) => handleParameterChange(param.name, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </fieldset>
        )}

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
            onClick={handleClone}
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" aria-hidden="true" /> Cloning…
              </>
            ) : (
              "Clone"
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
