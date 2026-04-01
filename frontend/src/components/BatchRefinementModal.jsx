import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { sendBatchChat } from "../api";
import QuickActionChips from "./QuickActionChips";
import ContentDiffView from "./ContentDiffView";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONTENT_TYPE_LABELS = {
  headline_cta: "Headline & CTA",
  headline: "Headline",
  cta: "CTA",
  social_post: "Social Post",
  ad_copy: "Ad Copy",
  tagline: "Tagline",
  body_copy: "Body Copy",
  email_subject: "Email Subject",
  email_body: "Email Body",
};

const STATUS_ICONS = {
  pending: "⏳",
  processing: "⚙️",
  done: "✅",
  failed: "❌",
};

function formatChannelLabel(channel) {
  if (!channel) return "";
  return String(channel)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function getChannelClassSuffix(channel) {
  if (!channel) return "default";
  const normalized = String(channel)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "default";
}

// ---------------------------------------------------------------------------
// BatchRefinementModal
// ---------------------------------------------------------------------------

export default function BatchRefinementModal({
  isOpen,
  onClose,
  campaignId,
  workspaceId,
  pieces = [],
  onBatchComplete,
}) {
  const [selectedIndices, setSelectedIndices] = useState(new Set());
  const [instruction, setInstruction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState(null); // null = not submitted yet
  const [error, setError] = useState(null);
  const [diffOpenIndex, setDiffOpenIndex] = useState(null);

  const dialogRef = useRef(null);
  const cancelRef = useRef(null);

  // Eligible pieces: exclude already-approved pieces
  const eligiblePieces = pieces
    .map((piece, idx) => ({ piece, idx }))
    .filter(({ piece }) => piece.approval_status !== "approved");

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      // Pre-select all eligible
      setSelectedIndices(new Set(eligiblePieces.map(({ idx }) => idx)));
      setInstruction("");
      setSubmitting(false);
      setResults(null);
      setError(null);
      setDiffOpenIndex(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Focus management
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
        if (!submitting) onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
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
  }, [isOpen, onClose, submitting]);

  // ---------------------------------------------------------------------------
  // Selection helpers
  // ---------------------------------------------------------------------------

  const toggleIndex = (idx) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIndices.size === eligiblePieces.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(eligiblePieces.map(({ idx }) => idx)));
    }
  };

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(async () => {
    if (selectedIndices.size === 0 || !instruction.trim()) return;
    setSubmitting(true);
    setError(null);

    // Set initial statuses
    const pieceIndices = Array.from(selectedIndices);
    const initialStatus = {};
    pieceIndices.forEach((idx) => {
      initialStatus[idx] = { status: "processing", before: null, after: null, error: null };
    });
    setResults(initialStatus);

    try {
      const response = await sendBatchChat(workspaceId, campaignId, {
        instruction: instruction.trim(),
        piece_indices: pieceIndices,
        context: {},
      });

      // Process results — response can be { results: [...] } or an array
      const resultList = Array.isArray(response) ? response : response?.results ?? [];
      const updatedResults = { ...initialStatus };

      resultList.forEach((r) => {
        const idx = r.piece_index ?? r.pieceIndex;
        if (idx != null) {
          updatedResults[idx] = {
            status: r.error ? "failed" : "done",
            before: r.before ?? r.original ?? "",
            after: r.after ?? r.refined_content ?? r.content ?? "",
            error: r.error ?? null,
          };
        }
      });

      // Mark any indices not in results as failed
      pieceIndices.forEach((idx) => {
        if (!updatedResults[idx] || updatedResults[idx].status === "processing") {
          updatedResults[idx] = { ...updatedResults[idx], status: "failed", error: "No response received" };
        }
      });

      setResults(updatedResults);
      onBatchComplete?.(resultList);
    } catch (err) {
      setError(err.message || "Batch refinement failed.");
      // Mark all as failed
      const failedResults = {};
      pieceIndices.forEach((idx) => {
        failedResults[idx] = { status: "failed", before: null, after: null, error: err.message };
      });
      setResults(failedResults);
    } finally {
      setSubmitting(false);
    }
  }, [selectedIndices, instruction, workspaceId, campaignId, onBatchComplete]);

  // ---------------------------------------------------------------------------
  // Quick action chip click
  // ---------------------------------------------------------------------------

  const handleChipClick = useCallback((chipInstruction) => {
    setInstruction(chipInstruction);
  }, []);

  // ---------------------------------------------------------------------------
  // Summary
  // ---------------------------------------------------------------------------

  const resultsSummary = results
    ? (() => {
        const entries = Object.values(results);
        const done = entries.filter((r) => r.status === "done").length;
        return `${done}/${entries.length} pieces refined successfully`;
      })()
    : null;

  if (!isOpen) return null;

  return createPortal(
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="batch-modal-title">
      <div className="modal-box card batch-modal" ref={dialogRef}>
        {/* Header */}
        <div className="modal-header">
          <h2 id="batch-modal-title">✨ Batch Refine</h2>
          <button
            ref={cancelRef}
            type="button"
            className="modal-close btn btn-sm btn-outline"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close batch refine modal"
          >
            ✕
          </button>
        </div>

        {/* Piece selector */}
        <div className="batch-modal-section">
          <div className="batch-modal-section-header">
            <span className="batch-modal-section-label">Select pieces</span>
            <button
              type="button"
              className="btn btn-sm btn-outline"
              onClick={toggleAll}
              disabled={submitting}
            >
              {selectedIndices.size === eligiblePieces.length ? "Deselect all" : "Select all"}
            </button>
          </div>
          <div className="batch-modal-pieces" role="group" aria-label="Content pieces to refine">
            {eligiblePieces.length === 0 && (
              <p className="batch-modal-empty">No eligible pieces — all pieces are already approved.</p>
            )}
            {eligiblePieces.map(({ piece, idx }) => {
              const sourceContent = piece.human_edited_content || piece.content || "";
              const preview = sourceContent.slice(0, 140) + (sourceContent.length > 140 ? "…" : "");
              const typeLabel = CONTENT_TYPE_LABELS[piece.content_type] || piece.content_type;
              const channelLabel = formatChannelLabel(piece.channel);
              const channelBadgeClass = `batch-modal-piece-channel-badge batch-modal-piece-channel-badge--${getChannelClassSuffix(piece.channel)}`;
              return (
                <label key={idx} className="batch-modal-piece-row">
                  <input
                    type="checkbox"
                    checked={selectedIndices.has(idx)}
                    onChange={() => toggleIndex(idx)}
                    disabled={submitting}
                  />
                  <span className="batch-modal-piece-info">
                    <span className="batch-modal-piece-meta">
                      <span className="batch-modal-piece-type">{typeLabel}</span>
                      {piece.channel && <span className={channelBadgeClass}>{channelLabel}</span>}
                    </span>
                    <span className="batch-modal-piece-preview">{preview}</span>
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Instruction input */}
        <div className="batch-modal-section">
          <label className="batch-modal-section-label" htmlFor="batch-instruction">
            Instruction
          </label>
          <textarea
            id="batch-instruction"
            className="batch-modal-textarea"
            placeholder="Describe how to refine the selected pieces…"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={3}
            disabled={submitting}
          />
        </div>

        {/* Quick action chips */}
        <div className="batch-modal-chips">
          <QuickActionChips
            onChipClick={handleChipClick}
          />
        </div>

        {/* Error */}
        {error && (
          <div className="batch-modal-error" role="alert">⚠ {error}</div>
        )}

        {/* Submit */}
        <div className="batch-modal-actions">
          <button
            type="button"
            className="btn btn-outline"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={submitting || selectedIndices.size === 0 || !instruction.trim()}
            onClick={handleSubmit}
          >
            {submitting ? (
              <><span className="spinner" aria-hidden="true" /> Processing…</>
            ) : (
              `Apply to Selected (${selectedIndices.size} piece${selectedIndices.size !== 1 ? "s" : ""})`
            )}
          </button>
        </div>

        {/* Results area */}
        {results && (
          <div className="batch-modal-results" data-testid="batch-results">
            {resultsSummary && (
              <div className="batch-modal-summary">{resultsSummary}</div>
            )}
            <div className="batch-modal-result-list">
              {Object.entries(results).map(([idxStr, result]) => {
                const idx = Number(idxStr);
                const piece = pieces[idx];
                const typeLabel = CONTENT_TYPE_LABELS[piece?.content_type] || piece?.content_type || "Piece";
                return (
                  <div key={idx} className="batch-modal-result-item">
                    <div className="batch-modal-result-header">
                      <span className="batch-modal-result-status">
                        {STATUS_ICONS[result.status] || "⏳"} {typeLabel} #{idx + 1}
                      </span>
                      {result.status === "done" && (
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          onClick={() => setDiffOpenIndex(diffOpenIndex === idx ? null : idx)}
                          aria-expanded={diffOpenIndex === idx}
                        >
                          {diffOpenIndex === idx ? "Hide diff" : "Show diff"}
                        </button>
                      )}
                      {result.status === "failed" && result.error && (
                        <span className="batch-modal-result-error">{result.error}</span>
                      )}
                    </div>
                    {diffOpenIndex === idx && result.status === "done" && (
                      <ContentDiffView
                        original={result.before || ""}
                        revised={result.after || ""}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
