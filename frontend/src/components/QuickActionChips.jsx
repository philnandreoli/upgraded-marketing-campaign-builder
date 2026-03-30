import { useState } from "react";

// ---------------------------------------------------------------------------
// Default chip sets per content type
// ---------------------------------------------------------------------------

const BASE_CHIPS = [
  "Make shorter",
  "More formal",
  "More casual",
  "Add urgency",
  "Simplify language",
  "Strengthen CTA",
  "Match brand voice",
];

const TYPE_CHIPS = {
  social_post: ["Add hashtags", "Shorten for platform"],
  email_subject: ["Improve subject line", "Add personalization"],
  email_body: ["Improve subject line", "Add personalization"],
  ad_copy: ["Highlight benefit", "Add social proof"],
};

function getDefaultChips(contentType) {
  const extra = TYPE_CHIPS[contentType] || [];
  return [...BASE_CHIPS, ...extra];
}

// ---------------------------------------------------------------------------
// QuickActionChips
// ---------------------------------------------------------------------------

export default function QuickActionChips({
  contentType,
  onChipClick,
  suggestedChips = [],
  customChips = [],
  onSaveCustomChip,
  onDeleteCustomChip,
}) {
  const [showAddInput, setShowAddInput] = useState(false);
  const [newChipText, setNewChipText] = useState("");

  const defaultChips = getDefaultChips(contentType);

  const handleAdd = () => {
    const trimmed = newChipText.trim();
    if (!trimmed) return;
    onSaveCustomChip?.(trimmed);
    setNewChipText("");
    setShowAddInput(false);
  };

  const handleAddKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAdd();
    }
    if (e.key === "Escape") {
      setShowAddInput(false);
      setNewChipText("");
    }
  };

  return (
    <div className="quick-action-chips" role="toolbar" aria-label="Quick refinement actions">
      <div className="quick-action-chips-scroll">
        {/* Suggested chips (highlighted) */}
        {suggestedChips.map((chip, idx) => (
          <button
            key={`sug-${idx}`}
            type="button"
            className="quick-action-chip quick-action-chip--suggested"
            onClick={() => onChipClick(chip)}
            title={chip}
          >
            ✨ {chip}
          </button>
        ))}

        {/* Default chips */}
        {defaultChips.map((chip) => (
          <button
            key={chip}
            type="button"
            className="quick-action-chip"
            onClick={() => onChipClick(chip)}
            title={chip}
          >
            {chip}
          </button>
        ))}

        {/* Custom chips */}
        {customChips.map((chip, idx) => (
          <span key={`custom-${idx}`} className="quick-action-chip quick-action-chip--custom">
            <button
              type="button"
              className="quick-action-chip-label"
              onClick={() => onChipClick(chip)}
              title={chip}
            >
              {chip}
            </button>
            {onDeleteCustomChip && (
              <button
                type="button"
                className="quick-action-chip-delete"
                onClick={() => onDeleteCustomChip(chip)}
                aria-label={`Delete custom chip: ${chip}`}
              >
                ×
              </button>
            )}
          </span>
        ))}

        {/* Add custom chip */}
        {onSaveCustomChip && (
          showAddInput ? (
            <span className="quick-action-chip quick-action-chip--add-input">
              <input
                type="text"
                className="quick-action-chip-input"
                value={newChipText}
                onChange={(e) => setNewChipText(e.target.value)}
                onKeyDown={handleAddKeyDown}
                onBlur={() => {
                  if (!newChipText.trim()) {
                    setShowAddInput(false);
                  }
                }}
                placeholder="Type chip…"
                autoFocus
                aria-label="New custom chip text"
              />
              <button
                type="button"
                className="quick-action-chip-confirm"
                onClick={handleAdd}
                disabled={!newChipText.trim()}
                aria-label="Save custom chip"
              >
                ✓
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="quick-action-chip quick-action-chip--add"
              onClick={() => setShowAddInput(true)}
              aria-label="Add custom chip"
            >
              +
            </button>
          )
        )}
      </div>
    </div>
  );
}
