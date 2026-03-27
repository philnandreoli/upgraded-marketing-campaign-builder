import { useEffect, useRef } from "react";

/**
 * MentionAutocomplete — dropdown list of campaign members triggered by "@".
 *
 * Props:
 *   members        – Array of { user_id, display_name, email }
 *   query          – The search text after "@" (e.g. "ali" for "@ali")
 *   onSelect       – Called with the selected member object
 *   anchorPosition – { top, left } pixel coords to position the dropdown
 *   activeIndex    – Index of the currently highlighted item (keyboard nav)
 */
export default function MentionAutocomplete({
  members,
  query,
  onSelect,
  anchorPosition,
  activeIndex: externalActiveIndex,
}) {
  const listRef = useRef(null);

  // Filter members by query (display_name or email prefix, case-insensitive)
  const lowerQuery = (query || "").toLowerCase();
  const filtered = members.filter((m) => {
    const name = (m.display_name || "").toLowerCase();
    const email = (m.email || "").toLowerCase();
    return name.includes(lowerQuery) || email.includes(lowerQuery);
  });

  const activeIndex = externalActiveIndex != null
    ? Math.min(externalActiveIndex, filtered.length - 1)
    : 0;

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-mention-item]");
    if (items[activeIndex] && items[activeIndex].scrollIntoView) {
      items[activeIndex].scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex]);

  if (filtered.length === 0) return null;

  return (
    <div
      className="mention-autocomplete"
      style={{
        ...(anchorPosition?.top != null ? { top: anchorPosition.top } : {}),
        ...(anchorPosition?.bottom != null ? { bottom: anchorPosition.bottom } : {}),
        left: anchorPosition?.left ?? 0,
        ...(anchorPosition?.marginBottom != null ? { marginBottom: anchorPosition.marginBottom } : {}),
      }}
      role="listbox"
      aria-label="Mention suggestions"
      ref={listRef}
    >
      {filtered.map((member, idx) => (
        <div
          key={member.user_id}
          className={`mention-autocomplete-item${idx === activeIndex ? " mention-autocomplete-item--active" : ""}`}
          role="option"
          aria-selected={idx === activeIndex}
          data-mention-item
          onMouseDown={(e) => {
            e.preventDefault(); // prevent textarea blur
            onSelect(member);
          }}
        >
          <span className="mention-autocomplete-avatar">
            {(member.display_name || "?")[0].toUpperCase()}
          </span>
          <span className="mention-autocomplete-info">
            <span className="mention-autocomplete-name">
              {member.display_name || member.user_id}
            </span>
            {member.email && (
              <span className="mention-autocomplete-email">{member.email}</span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
