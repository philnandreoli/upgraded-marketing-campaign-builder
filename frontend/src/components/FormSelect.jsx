import { useState, useRef, useEffect } from "react";

/**
 * FormSelect — custom themed dropdown for form fields.
 * Full-width, inherits form-group sizing, fully themed via CSS variables.
 *
 * Props:
 *   options   — array of { value, label }
 *   value     — currently selected value
 *   onChange  — fn(value) called when selection changes
 *   id        — id for accessibility (label htmlFor)
 *   ariaLabel — fallback accessible label
 *   placeholder — text when no value selected
 */
export default function FormSelect({
  options,
  value,
  onChange,
  id,
  ariaLabel,
  placeholder = "Select…",
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const listRef = useRef(null);
  const triggerRef = useRef(null);

  const selectedOption = options.find((o) => o.value === value);
  const displayLabel = selectedOption?.label ?? placeholder;

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
        triggerRef.current?.focus();
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const idx = options.findIndex((o) => o.value === value);
        const next =
          e.key === "ArrowDown"
            ? Math.min(idx + 1, options.length - 1)
            : Math.max(idx - 1, 0);
        onChange(options[next].value);
      }
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, value, options, onChange]);

  const handleSelect = (val) => {
    onChange(val);
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div className="form-select-custom" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`form-select-custom__trigger${open ? " form-select-custom__trigger--open" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        id={id}
      >
        <span className="form-select-custom__label">{displayLabel}</span>
        <svg
          className={`form-select-custom__chevron${open ? " form-select-custom__chevron--open" : ""}`}
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
          className="form-select-custom__menu"
          role="listbox"
          aria-label={ariaLabel || displayLabel}
        >
          {options.map((opt) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              className={`form-select-custom__item${opt.value === value ? " form-select-custom__item--active" : ""}`}
              onClick={() => handleSelect(opt.value)}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
