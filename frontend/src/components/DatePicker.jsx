import { useState, useRef, useEffect } from "react";

const DAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function getDaysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfWeek(year, month) {
  return new Date(year, month, 1).getDay();
}

function formatDate(y, m, d) {
  return `${String(y)}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function parseDate(str) {
  if (!str) return null;
  const [y, m, d] = str.split("-").map(Number);
  return { year: y, month: m - 1, day: d };
}

function formatDisplay(str) {
  if (!str) return "";
  const [y, m, d] = str.split("-");
  return `${m}/${d}/${y}`;
}

export default function DatePicker({ value, onChange, min, placeholder = "mm/dd/yyyy" }) {
  const [open, setOpen] = useState(false);
  const parsed = parseDate(value);
  const today = new Date();
  const [viewYear, setViewYear] = useState(parsed?.year ?? today.getFullYear());
  const [viewMonth, setViewMonth] = useState(parsed?.month ?? today.getMonth());
  const ref = useRef(null);

  const toggleOpen = () => {
    setOpen((o) => {
      if (!o && parsed) {
        setViewYear(parsed.year);
        setViewMonth(parsed.month);
      }
      return !o;
    });
  };

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear((y) => y - 1); }
    else setViewMonth((m) => m - 1);
  };
  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear((y) => y + 1); }
    else setViewMonth((m) => m + 1);
  };

  const daysInMonth = getDaysInMonth(viewYear, viewMonth);
  const firstDay = getFirstDayOfWeek(viewYear, viewMonth);

  const prevMonthDays = getDaysInMonth(viewYear, viewMonth === 0 ? 11 : viewMonth - 1);
  const leadingBlanks = firstDay;
  const trailingBlanks = (7 - ((leadingBlanks + daysInMonth) % 7)) % 7;

  const minParsed = parseDate(min);

  function isDisabled(day) {
    if (!minParsed) return false;
    const cellDate = new Date(viewYear, viewMonth, day);
    const minDate = new Date(minParsed.year, minParsed.month, minParsed.day);
    return cellDate < minDate;
  }

  function isToday(day) {
    return viewYear === today.getFullYear() && viewMonth === today.getMonth() && day === today.getDate();
  }

  function isSelected(day) {
    return parsed && viewYear === parsed.year && viewMonth === parsed.month && day === parsed.day;
  }

  function selectDay(day) {
    const dateStr = formatDate(viewYear, viewMonth, day);
    onChange({ target: { value: dateStr } });
    setOpen(false);
  }

  function handleClear() {
    onChange({ target: { value: "" } });
    setOpen(false);
  }

  function handleToday() {
    const t = new Date();
    setViewYear(t.getFullYear());
    setViewMonth(t.getMonth());
    selectDay(t.getDate());
  }

  return (
    <div className="datepicker" ref={ref}>
      <button
        type="button"
        className="datepicker-trigger"
        onClick={toggleOpen}
      >
        <span className={value ? "datepicker-value" : "datepicker-placeholder"}>
          {value ? formatDisplay(value) : placeholder}
        </span>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="datepicker-icon">
          <rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
          <line x1="2" y1="6.5" x2="14" y2="6.5" stroke="currentColor" strokeWidth="1.3" />
          <line x1="5.5" y1="2" x2="5.5" y2="4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <line x1="10.5" y1="2" x2="10.5" y2="4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div className="datepicker-dropdown">
          <div className="datepicker-header">
            <button type="button" className="datepicker-nav" onClick={prevMonth} aria-label="Previous month">
              ‹
            </button>
            <span className="datepicker-month-label">
              {MONTHS[viewMonth]} {viewYear}
            </span>
            <button type="button" className="datepicker-nav" onClick={nextMonth} aria-label="Next month">
              ›
            </button>
          </div>

          <div className="datepicker-grid">
            {DAYS.map((d) => (
              <div key={d} className="datepicker-weekday">{d}</div>
            ))}

            {Array.from({ length: leadingBlanks }, (_, i) => (
              <div key={`lb-${i}`} className="datepicker-day datepicker-day--outside">
                {prevMonthDays - leadingBlanks + i + 1}
              </div>
            ))}

            {Array.from({ length: daysInMonth }, (_, i) => {
              const day = i + 1;
              const disabled = isDisabled(day);
              return (
                <button
                  key={day}
                  type="button"
                  disabled={disabled}
                  className={
                    "datepicker-day" +
                    (isSelected(day) ? " datepicker-day--selected" : "") +
                    (isToday(day) ? " datepicker-day--today" : "") +
                    (disabled ? " datepicker-day--disabled" : "")
                  }
                  onClick={() => selectDay(day)}
                >
                  {day}
                </button>
              );
            })}

            {Array.from({ length: trailingBlanks }, (_, i) => (
              <div key={`tb-${i}`} className="datepicker-day datepicker-day--outside">
                {i + 1}
              </div>
            ))}
          </div>

          <div className="datepicker-footer">
            <button type="button" className="datepicker-footer-btn" onClick={handleClear}>Clear</button>
            <button type="button" className="datepicker-footer-btn datepicker-footer-btn--primary" onClick={handleToday}>Today</button>
          </div>
        </div>
      )}
    </div>
  );
}
