import { useState } from "react";
import { MAX_SAVED_VIEWS } from "../hooks/useSavedViews";
import { FILTER_TABS } from "../constants/statusGroups";

/**
 * SavedViews — chip/pill row showing user-created saved views.
 *
 * Props:
 *   activeFilter   string   — currently active filter tab id
 *   searchQuery    string   — current (debounced) search query
 *   views          array    — user-created saved views from useSavedViews
 *   onApply        fn       — (filter, search) called when a view is clicked
 *   onAdd          fn       — (name, filter, search) → bool; create new view
 *   onRemove       fn       — (id) delete a saved view
 *   onRename       fn       — (id, name) rename a saved view
 */
export default function SavedViews({
  activeFilter,
  searchQuery,
  views,
  onApply,
  onAdd,
  onRemove,
  onRename,
}) {
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveError, setSaveError] = useState("");
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");

  // Determine if current state differs from the default (all + no search)
  const isNonDefault = activeFilter !== "all" || searchQuery.trim() !== "";

  const handleSaveClick = () => {
    // Pre-fill name from filter label + query
    const tab = FILTER_TABS.find((t) => t.id === activeFilter);
    const filterLabel = tab?.label ?? activeFilter;
    const suggested = searchQuery.trim()
      ? `${filterLabel} — ${searchQuery.trim()}`
      : filterLabel;
    setSaveName(suggested);
    setSaveError("");
    setShowSaveDialog(true);
  };

  const handleSaveConfirm = () => {
    const name = saveName.trim();
    if (!name) {
      setSaveError("Please enter a name for this view.");
      return;
    }
    const success = onAdd(name, activeFilter, searchQuery.trim());
    if (!success) {
      setSaveError(
        `You've reached the maximum of ${MAX_SAVED_VIEWS} saved views. Delete one to add a new view.`
      );
      return;
    }
    setShowSaveDialog(false);
    setSaveName("");
    setSaveError("");
  };

  const handleSaveCancel = () => {
    setShowSaveDialog(false);
    setSaveName("");
    setSaveError("");
  };

  const handleSaveKeyDown = (e) => {
    if (e.key === "Enter") handleSaveConfirm();
    if (e.key === "Escape") handleSaveCancel();
  };

  const startRename = (view) => {
    setRenamingId(view.id);
    setRenameValue(view.name);
  };

  const commitRename = () => {
    if (renameValue.trim() && renamingId) {
      onRename(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue("");
  };

  const handleRenameKeyDown = (e) => {
    if (e.key === "Enter") commitRename();
    if (e.key === "Escape") {
      setRenamingId(null);
      setRenameValue("");
    }
  };

  if (views.length === 0 && !isNonDefault) {
    return null;
  }

  return (
    <div className="saved-views">
      <div className="saved-views__row" role="group" aria-label="Saved views">
        {/* User-created views */}
        {views.map((view) => {
          const isActive =
            activeFilter === view.filter && searchQuery.trim() === view.search;
          return renamingId === view.id ? (
            <span key={view.id} className="saved-view-chip saved-view-chip--renaming">
              <input
                className="saved-view-chip__rename-input"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={commitRename}
                onKeyDown={handleRenameKeyDown}
                aria-label="Rename view"
                autoFocus
              />
            </span>
          ) : (
            <span
              key={view.id}
              className={`saved-view-chip saved-view-chip--user${isActive ? " saved-view-chip--active" : ""}`}
            >
              <button
                type="button"
                className="saved-view-chip__label"
                onClick={() => onApply(view.filter, view.search)}
                aria-label={`Apply saved view: ${view.name}`}
              >
                {view.name}
              </button>
              <button
                type="button"
                className="saved-view-chip__action"
                onClick={() => startRename(view)}
                aria-label={`Rename view: ${view.name}`}
                title="Rename"
              >
                <span aria-hidden="true">✏️</span>
              </button>
              <button
                type="button"
                className="saved-view-chip__action saved-view-chip__action--delete"
                onClick={() => onRemove(view.id)}
                aria-label={`Delete saved view: ${view.name}`}
                title="Delete"
              >
                <span aria-hidden="true">✕</span>
              </button>
            </span>
          );
        })}

        {/* Save current view button */}
        {isNonDefault && !showSaveDialog && views.length < MAX_SAVED_VIEWS && (
          <button
            type="button"
            className="saved-view-chip saved-view-chip--save"
            onClick={handleSaveClick}
            aria-label="Save current view"
          >
            + Save view
          </button>
        )}

        {/* At-limit message */}
        {isNonDefault && !showSaveDialog && views.length >= MAX_SAVED_VIEWS && (
          <span className="saved-views__limit-msg" role="status">
            Max {MAX_SAVED_VIEWS} views reached
          </span>
        )}
      </div>

      {/* Inline save dialog */}
      {showSaveDialog && (
        <div className="saved-views__save-dialog" role="dialog" aria-label="Save current view">
          <input
            type="text"
            className="saved-views__save-input"
            placeholder="View name…"
            value={saveName}
            onChange={(e) => {
              setSaveName(e.target.value);
              setSaveError("");
            }}
            onKeyDown={handleSaveKeyDown}
            aria-label="View name"
            autoFocus
          />
          <button
            type="button"
            className="saved-views__save-confirm"
            onClick={handleSaveConfirm}
          >
            Save
          </button>
          <button
            type="button"
            className="saved-views__save-cancel"
            onClick={handleSaveCancel}
          >
            Cancel
          </button>
          {saveError && (
            <span className="saved-views__save-error" role="alert">
              {saveError}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
