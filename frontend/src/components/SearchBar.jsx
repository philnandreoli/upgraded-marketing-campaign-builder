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
  const handleKeyDown = (e) => {
    if (e.key === "Escape" && value) {
      onClear();
    }
  };

  return (
    <div className="search-bar">
      <span className="search-bar__icon" aria-hidden="true">🔍</span>
      <input
        type="search"
        className="search-bar__input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
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
