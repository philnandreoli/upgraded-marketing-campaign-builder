import { useEffect, useRef } from "react";

/**
 * SearchBar — campaign search input with clear button.
 *
 * Props:
 *   value       string  — controlled search query value
 *   onChange    fn      — called with new string value on every keystroke
 *   onClear     fn      — called when the user clears the search
 *   placeholder string  — optional placeholder text (default: "Search campaigns...")
 */
export default function SearchBar({ value, onChange, onClear, placeholder = "Search campaigns..." }) {
  const inputRef = useRef(null);

  // Allow Escape key to clear the search from anywhere the input is focused
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && value) {
        onClear();
      }
    };
    input.addEventListener("keydown", handleKeyDown);
    return () => input.removeEventListener("keydown", handleKeyDown);
  }, [value, onClear]);

  return (
    <div className="search-bar">
      <span className="search-bar__icon" aria-hidden="true">🔍</span>
      <input
        ref={inputRef}
        type="search"
        className="search-bar__input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search campaigns"
      />
      {value && (
        <button
          type="button"
          className="search-bar__clear"
          onClick={onClear}
          aria-label="Clear search"
        >
          ✕
        </button>
      )}
    </div>
  );
}
