import { useState, useRef, useEffect } from "react";

/**
 * SortDropdown — custom themed dropdown that replaces the native <select>
 * for campaign sorting. Fully respects dark/light theme via CSS variables.
 *
 * Props:
 *   options   — array of { id, label }
 *   value     — currently selected option id
 *   onChange  — fn(value) called when an option is selected
 *   ariaLabel — accessible label for the control
 */
export default function SortDropdown({ options, value, onChange, ariaLabel = "Sort" }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const listRef = useRef(null);
  const selectedOption = options.find((o) => o.id === value) ?? options[0];

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const idx = options.findIndex((o) => o.id === value);
        const next =
          e.key === "ArrowDown"
            ? Math.min(idx + 1, options.length - 1)
            : Math.max(idx - 1, 0);
        onChange(options[next].id);
      }
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, value, options, onChange]);

  const handleSelect = (id) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div className="sort-dropdown" ref={containerRef}>
      <button
        type="button"
        className="sort-dropdown__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
      >
        <span className="sort-dropdown__label">{selectedOption.label}</span>
        <svg
          className={`sort-dropdown__chevron${open ? " sort-dropdown__chevron--open" : ""}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <polyline
            points="6 9 12 15 18 9"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <ul
          ref={listRef}
          className="sort-dropdown__menu"
          role="listbox"
          aria-label={ariaLabel}
        >
          {options.map((opt) => (
            <li
              key={opt.id}
              role="option"
              aria-selected={opt.id === value}
              className={`sort-dropdown__item${opt.id === value ? " sort-dropdown__item--active" : ""}`}
              onClick={() => handleSelect(opt.id)}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
