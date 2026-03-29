import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getTemplatePreview, ApiError } from "../api";

/**
 * TemplatePreviewModal — full-width modal showing read-only campaign data
 * fetched via getTemplatePreview(id).
 *
 * Props:
 *   isOpen          boolean
 *   onClose         () => void
 *   templateId      string          — template ID to fetch preview for
 *   templateName    string          — display name fallback while loading
 *   onUseTemplate   (template) => void — called when user clicks "Use This Template"
 */
export default function TemplatePreviewModal({
  isOpen,
  onClose,
  templateId,
  templateName,
  onUseTemplate,
}) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);

  // Fetch preview data
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!isOpen || !templateId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    getTemplatePreview(templateId)
      .then((data) => {
        if (!cancelled) {
          setPreview(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setError(err.message || "Failed to load template preview.");
          } else {
            setError("Network error — please check your connection and try again.");
          }
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [isOpen, templateId]);

  // Focus close button on open
  useEffect(() => {
    if (isOpen && closeRef.current) {
      closeRef.current.focus();
    }
  }, [isOpen, loading]);

  // Escape key + focus trap
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
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
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const brief = preview?.brief;
  const strategy = preview?.strategy;
  const content = preview?.content;
  const channelPlan = preview?.channel_plan;
  const analyticsPlan = preview?.analytics_plan;
  const parameters = preview?.template_parameters;

  return createPortal(
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="template-preview-title"
    >
      <div className="modal-box card template-preview-modal" ref={dialogRef}>
        <div className="modal-header">
          <h2 id="template-preview-title">
            {preview?.name || templateName || "Template Preview"}
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="modal-close btn btn-outline"
            onClick={onClose}
            aria-label="Close preview"
          >
            ✕
          </button>
        </div>

        <div className="template-preview-body">
          {loading && (
            <div className="template-preview-loading" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              Loading preview…
            </div>
          )}

          {error && (
            <div className="template-preview-error" role="alert">
              {error}
            </div>
          )}

          {!loading && !error && preview && (
            <>
              {/* Brief Section */}
              {brief && (
                <section className="template-preview-section">
                  <h3>Brief</h3>
                  <dl className="template-preview-dl">
                    {brief.product && (
                      <>
                        <dt>Product</dt>
                        <dd>{brief.product}</dd>
                      </>
                    )}
                    {brief.goal && (
                      <>
                        <dt>Goal</dt>
                        <dd>{brief.goal}</dd>
                      </>
                    )}
                    {brief.budget && (
                      <>
                        <dt>Budget</dt>
                        <dd>{brief.budget}</dd>
                      </>
                    )}
                    {(brief.start_date || brief.end_date) && (
                      <>
                        <dt>Date Range</dt>
                        <dd>
                          {brief.start_date || "—"} → {brief.end_date || "—"}
                        </dd>
                      </>
                    )}
                    {brief.channels && brief.channels.length > 0 && (
                      <>
                        <dt>Channels</dt>
                        <dd>{brief.channels.join(", ")}</dd>
                      </>
                    )}
                  </dl>
                </section>
              )}

              {/* Strategy Section */}
              {strategy && (
                <section className="template-preview-section">
                  <h3>Strategy</h3>
                  <dl className="template-preview-dl">
                    {strategy.objectives && (
                      <>
                        <dt>Objectives</dt>
                        <dd>{strategy.objectives}</dd>
                      </>
                    )}
                    {strategy.target_audience && (
                      <>
                        <dt>Target Audience</dt>
                        <dd>{strategy.target_audience}</dd>
                      </>
                    )}
                    {strategy.value_proposition && (
                      <>
                        <dt>Value Proposition</dt>
                        <dd>{strategy.value_proposition}</dd>
                      </>
                    )}
                    {strategy.key_messages && strategy.key_messages.length > 0 && (
                      <>
                        <dt>Key Messages</dt>
                        <dd>
                          <ul className="template-preview-list">
                            {strategy.key_messages.map((msg, i) => (
                              <li key={i}>{msg}</li>
                            ))}
                          </ul>
                        </dd>
                      </>
                    )}
                  </dl>
                </section>
              )}

              {/* Content Section */}
              {content && (
                <section className="template-preview-section">
                  <h3>Content</h3>
                  {content.theme && (
                    <p className="template-preview-meta">
                      <strong>Theme:</strong> {content.theme}
                    </p>
                  )}
                  {content.tone && (
                    <p className="template-preview-meta">
                      <strong>Tone:</strong> {content.tone}
                    </p>
                  )}
                  {content.pieces && content.pieces.length > 0 && (
                    <div className="template-preview-pieces">
                      {content.pieces.map((piece, i) => (
                        <div key={i} className="template-preview-piece">
                          <span className="badge badge-strategy">
                            {piece.type || "content"}
                          </span>
                          {piece.channel && (
                            <span className="template-preview-piece-channel">
                              {piece.channel}
                            </span>
                          )}
                          {piece.content && (
                            <p className="template-preview-piece-content">
                              {piece.content.length > 200
                                ? piece.content.slice(0, 200) + "…"
                                : piece.content}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* Channel Plan Section */}
              {channelPlan && (
                <section className="template-preview-section">
                  <h3>Channel Plan</h3>
                  {channelPlan.budget_allocation && (
                    <p className="template-preview-meta">
                      <strong>Budget Allocation:</strong>{" "}
                      {typeof channelPlan.budget_allocation === "string"
                        ? channelPlan.budget_allocation
                        : JSON.stringify(channelPlan.budget_allocation)}
                    </p>
                  )}
                  {channelPlan.recommendations &&
                    channelPlan.recommendations.length > 0 && (
                      <ul className="template-preview-list">
                        {channelPlan.recommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ul>
                    )}
                </section>
              )}

              {/* Analytics Plan Section */}
              {analyticsPlan && (
                <section className="template-preview-section">
                  <h3>Analytics Plan</h3>
                  {analyticsPlan.kpis && analyticsPlan.kpis.length > 0 && (
                    <>
                      <p className="template-preview-meta">
                        <strong>KPIs:</strong>
                      </p>
                      <ul className="template-preview-list">
                        {analyticsPlan.kpis.map((kpi, i) => (
                          <li key={i}>{typeof kpi === "string" ? kpi : kpi.name || JSON.stringify(kpi)}</li>
                        ))}
                      </ul>
                    </>
                  )}
                  {analyticsPlan.tracking_tools &&
                    analyticsPlan.tracking_tools.length > 0 && (
                      <p className="template-preview-meta">
                        <strong>Tracking Tools:</strong>{" "}
                        {analyticsPlan.tracking_tools.join(", ")}
                      </p>
                    )}
                </section>
              )}

              {/* Parameters Section */}
              {parameters && parameters.length > 0 && (
                <section className="template-preview-section">
                  <h3>Template Parameters</h3>
                  <div className="template-preview-params">
                    {parameters.map((param, i) => (
                      <div key={i} className="template-preview-param">
                        <span className="template-preview-param-name">
                          {param.name}
                        </span>
                        <span className="badge badge-strategy">{param.type}</span>
                        {param.description && (
                          <span className="template-preview-param-desc">
                            {param.description}
                          </span>
                        )}
                        {param.default != null && (
                          <span className="template-preview-param-default">
                            Default: {String(param.default)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        {/* CTA */}
        {!loading && !error && preview && (
          <div className="template-preview-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onUseTemplate?.(preview)}
            >
              Use This Template
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
