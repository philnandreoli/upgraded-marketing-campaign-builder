import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/**
 * ConfirmDialog — a styled modal portal for confirmation prompts.
 *
 * Replaces native window.confirm() with a themed modal that supports
 * destructive styling, focus trapping, and Escape-key dismissal.
 *
 * Props:
 *   open        — whether the dialog is visible
 *   title       — heading text (e.g. "Delete campaign?")
 *   message     — body text explaining the action
 *   confirmLabel — label for the confirm button (default "Confirm")
 *   cancelLabel  — label for the cancel button (default "Cancel")
 *   destructive  — if true, the confirm button uses danger/red styling
 *   onConfirm    — called when the user confirms
 *   onCancel     — called when the user cancels (or presses Escape)
 */
export default function ConfirmDialog({
  open,
  title = "Are you sure?",
  message = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  onCancel,
}) {
  const cancelRef = useRef(null);
  const dialogRef = useRef(null);

  // Auto-focus the cancel button when the dialog opens
  useEffect(() => {
    if (open && cancelRef.current) {
      cancelRef.current.focus();
    }
  }, [open]);

  // Escape key dismissal + focus trapping
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }

      // Focus trap: cycle focus within the dialog
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
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
  }, [open, onCancel]);

  if (!open) return null;

  return createPortal(
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
      <div className="modal-box card confirm-dialog" ref={dialogRef}>
        <div className="modal-header">
          <h2 id="confirm-dialog-title">{title}</h2>
        </div>
        {message && (
          <p className="confirm-dialog-message">{message}</p>
        )}
        <div className="confirm-dialog-actions">
          <button
            ref={cancelRef}
            type="button"
            className="btn btn-outline"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${destructive ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
