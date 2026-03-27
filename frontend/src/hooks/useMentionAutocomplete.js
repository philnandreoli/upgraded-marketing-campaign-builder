import { useCallback, useState } from "react";

/**
 * Filter members by a query string (matches display_name or email, case-insensitive).
 */
function filterMembers(members, query) {
  const lowerQuery = (query || "").toLowerCase();
  return members.filter((m) => {
    const name = (m.display_name || "").toLowerCase();
    const email = (m.email || "").toLowerCase();
    return name.includes(lowerQuery) || email.includes(lowerQuery);
  });
}

/**
 * Hook to manage mention autocomplete state for a textarea.
 *
 * Returns:
 *   mentionState   – { active, query, anchorPosition, activeIndex } for rendering
 *   handleChange   – Wraps textarea onChange to detect @-trigger
 *   handleKeyDown  – Wraps textarea onKeyDown for keyboard nav
 *   insertMention  – Called when a member is selected
 *   dismissMention – Called to close the dropdown
 */
export function useMentionAutocomplete({ members, textareaRef, value, onChange }) {
  const [mentionState, setMentionState] = useState({
    active: false,
    query: "",
    startIndex: -1,
    anchorPosition: { top: 0, left: 0 },
    activeIndex: 0,
  });

  /**
   * Compute an approximate dropdown anchor based on the textarea element.
   */
  const computeAnchorPosition = useCallback((textarea) => {
    if (!textarea) return { top: 0, left: 0 };
    const rect = textarea.getBoundingClientRect();
    return {
      top: rect.bottom + 4,
      left: rect.left,
    };
  }, []);

  function handleChange(e) {
    const newValue = e.target.value;
    const cursorPos = e.target.selectionStart;
    onChange(newValue);

    const textBeforeCursor = newValue.slice(0, cursorPos);
    const atIdx = textBeforeCursor.lastIndexOf("@");

    if (atIdx === -1) {
      if (mentionState.active) {
        setMentionState((s) => ({ ...s, active: false }));
      }
      return;
    }

    // The character before "@" must be whitespace, start-of-string, or newline
    if (atIdx > 0) {
      const charBefore = textBeforeCursor[atIdx - 1];
      if (!/[\s\n]/.test(charBefore)) {
        if (mentionState.active) {
          setMentionState((s) => ({ ...s, active: false }));
        }
        return;
      }
    }

    // No spaces allowed in query text between "@" and cursor
    const queryText = textBeforeCursor.slice(atIdx + 1);
    if (/\s/.test(queryText)) {
      if (mentionState.active) {
        setMentionState((s) => ({ ...s, active: false }));
      }
      return;
    }

    const anchor = computeAnchorPosition(textareaRef?.current || e.target);
    setMentionState({
      active: true,
      query: queryText,
      startIndex: atIdx,
      anchorPosition: anchor,
      activeIndex: 0,
    });
  }

  function handleKeyDown(e) {
    if (!mentionState.active) return;
    const filtered = filterMembers(members, mentionState.query);
    if (filtered.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setMentionState((s) => ({
        ...s,
        activeIndex: Math.min(s.activeIndex + 1, filtered.length - 1),
      }));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setMentionState((s) => ({
        ...s,
        activeIndex: Math.max(s.activeIndex - 1, 0),
      }));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const member = filtered[mentionState.activeIndex];
      if (member) {
        insertMention(member);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      dismissMention();
    }
  }

  function insertMention(member) {
    const { startIndex } = mentionState;
    const textarea = textareaRef?.current;
    const cursorPos = textarea ? textarea.selectionStart : value.length;

    const token = `@[${member.user_id}:${member.display_name || member.user_id}]`;
    const before = value.slice(0, startIndex);
    const after = value.slice(cursorPos);
    const newValue = before + token + " " + after;
    onChange(newValue);

    setMentionState({
      active: false,
      query: "",
      startIndex: -1,
      anchorPosition: { top: 0, left: 0 },
      activeIndex: 0,
    });

    // Restore focus and cursor position after insertion
    requestAnimationFrame(() => {
      if (textarea) {
        textarea.focus();
        const pos = before.length + token.length + 1;
        textarea.setSelectionRange(pos, pos);
      }
    });
  }

  function dismissMention() {
    setMentionState({
      active: false,
      query: "",
      startIndex: -1,
      anchorPosition: { top: 0, left: 0 },
      activeIndex: 0,
    });
  }

  return {
    mentionState,
    handleChange,
    handleKeyDown,
    insertMention,
    dismissMention,
  };
}
