import { useCallback, useEffect, useState } from "react";
import { getCalendar } from "../api";

// Channel type to CSS color variable mapping
const CHANNEL_COLORS = {
  email:              { bg: "var(--cal-ch-email-bg)",    text: "var(--cal-ch-email-text)"    },
  social_media:       { bg: "var(--cal-ch-social-bg)",   text: "var(--cal-ch-social-text)"   },
  paid_ads:           { bg: "var(--cal-ch-paid-bg)",     text: "var(--cal-ch-paid-text)"     },
  content_marketing:  { bg: "var(--cal-ch-content-bg)",  text: "var(--cal-ch-content-text)"  },
  seo:                { bg: "var(--cal-ch-seo-bg)",      text: "var(--cal-ch-seo-text)"      },
  influencer:         { bg: "var(--cal-ch-influencer-bg)", text: "var(--cal-ch-influencer-text)" },
  events:             { bg: "var(--cal-ch-events-bg)",   text: "var(--cal-ch-events-text)"   },
  pr:                 { bg: "var(--cal-ch-pr-bg)",       text: "var(--cal-ch-pr-text)"       },
};

const CHANNEL_ICONS = {
  email:             "✉️",
  social_media:      "📱",
  paid_ads:          "💰",
  content_marketing: "📝",
  seo:               "🔍",
  influencer:        "⭐",
  events:            "🎪",
  pr:                "📣",
};

const CONTENT_TYPE_ICONS = {
  headline:      "✍️",
  body_copy:     "📄",
  cta:           "🎯",
  social_post:   "📱",
  email_subject: "✉️",
  image:         "🖼️",
};

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CAL_VIEW_MODE_KEY = "cal_view_mode";

// Hour labels for weekly time slots (6am–10pm)
const HOUR_START = 6;
const HOUR_END = 22;
const HOURS = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);

function truncate(str, max = 60) {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "…" : str;
}

function getChannelColor(channel) {
  return CHANNEL_COLORS[channel] || { bg: "var(--cal-ch-default-bg)", text: "var(--cal-ch-default-text)" };
}

function getContentIcon(contentType) {
  return CONTENT_TYPE_ICONS[contentType] || "📋";
}

function getChannelIcon(channel) {
  return CHANNEL_ICONS[channel] || "📡";
}

// Build a 6-row × 7-col grid of Date objects for the given year/month (0-indexed)
function buildCalendarGrid(year, month) {
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  // Leading empty cells
  for (let i = 0; i < firstDay; i++) cells.push(null);
  // Day cells
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  // Trailing empty cells to complete last row
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// Return the Sunday that starts the week containing the given date
function getWeekStart(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

// Format a date as "Mon D" or "Mon D, YYYY" if year differs from reference
function formatWeekDay(date, refYear) {
  const label = `${MONTH_SHORT[date.getMonth()]} ${date.getDate()}`;
  return date.getFullYear() !== refYear ? `${label}, ${date.getFullYear()}` : label;
}

// Parse a time string like "14:30:00" or "14:30" into fractional hours
function parseTimeFraction(timeStr) {
  if (!timeStr) return null;
  const parts = timeStr.split(":");
  const h = parseInt(parts[0], 10);
  const min = parseInt(parts[1] || "0", 10);
  return h + min / 60;
}

function ContentPieceCard({ calPiece }) {
  const { piece } = calPiece;
  const colors = getChannelColor(piece.channel);
  return (
    <div
      className="cal-piece-card"
      style={{ background: colors.bg, color: colors.text }}
      title={piece.content}
    >
      <span className="cal-piece-icon" aria-hidden="true">
        {getContentIcon(piece.content_type)}
      </span>
      <span className="cal-piece-text">{truncate(piece.content, 50)}</span>
      {piece.channel && (
        <span className="cal-piece-channel-badge" style={{ background: colors.bg, color: colors.text }}>
          {getChannelIcon(piece.channel)} {piece.channel.replace(/_/g, " ")}
        </span>
      )}
    </div>
  );
}

// Weekly view sub-component
function WeeklyView({ weekStart, piecesByDate, todayISO }) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(weekStart.getDate() + i);
    return d;
  });

  // Split pieces for each day into "all day" (no time) and timed
  const dayData = days.map((d) => {
    const iso = toISODate(d);
    const pieces = piecesByDate[iso] || [];
    const allDay = pieces.filter((cp) => !cp.piece.scheduled_time);
    const timed = pieces.filter((cp) => !!cp.piece.scheduled_time);
    return { date: d, iso, allDay, timed };
  });

  const slotHeight = 48; // px per hour slot
  const totalHeight = HOURS.length * slotHeight;

  return (
    <div className="cal-week-container">
      {/* Column headers */}
      <div className="cal-week-header-row">
        <div className="cal-week-time-gutter" />
        {days.map((d) => {
          const iso = toISODate(d);
          const isToday = iso === todayISO;
          return (
            <div key={iso} className={`cal-week-col-header${isToday ? " cal-week-col-header--today" : ""}`}>
              <span className="cal-week-col-weekday">{WEEKDAY_LABELS[d.getDay()]}</span>
              <span className={`cal-week-col-date${isToday ? " cal-day-number--today" : ""}`}>
                {d.getDate()}
              </span>
            </div>
          );
        })}
      </div>

      {/* All Day row */}
      <div className="cal-week-allday-row">
        <div className="cal-week-time-gutter cal-week-allday-label">All Day</div>
        {dayData.map(({ iso, allDay }) => (
          <div key={iso} className="cal-week-allday-cell">
            {allDay.map((cp) => (
              <ContentPieceCard key={cp.piece_index} calPiece={cp} />
            ))}
          </div>
        ))}
      </div>

      {/* Timed grid: time gutter + per-day columns */}
      <div className="cal-week-timed-outer" style={{ height: `${totalHeight}px` }}>
        {/* Time gutter */}
        <div className="cal-week-time-gutter cal-week-timed-gutter-col">
          {HOURS.map((h) => (
            <div
              key={h}
              className="cal-week-hour-label"
              style={{ top: `${(h - HOUR_START) * slotHeight}px`, height: `${slotHeight}px` }}
            >
              {h === 12 ? "12 PM" : h < 12 ? `${h} AM` : `${h - 12} PM`}
            </div>
          ))}
        </div>

        {/* Day columns */}
        {dayData.map(({ iso, timed }, colIdx) => {
          const isToday = iso === todayISO;
          return (
            <div key={iso} className={`cal-week-day-col${isToday ? " cal-week-day-col--today" : ""}`}>
              {/* Hour background rows */}
              {HOURS.map((h) => (
                <div
                  key={h}
                  className={`cal-week-hour-bg${h % 2 === 0 ? " cal-week-hour-bg--alt" : ""}`}
                  style={{ top: `${(h - HOUR_START) * slotHeight}px`, height: `${slotHeight}px` }}
                />
              ))}
              {/* Timed pieces */}
              {timed.map((cp) => {
                const timeFrac = parseTimeFraction(cp.piece.scheduled_time);
                if (timeFrac === null) return null;
                const topFrac = timeFrac - HOUR_START;
                const clampedTop = Math.max(0, Math.min(topFrac, HOURS.length - 0.5));
                return (
                  <div
                    key={cp.piece_index}
                    className="cal-week-timed-piece"
                    style={{ top: `${clampedTop * slotHeight}px` }}
                  >
                    <ContentPieceCard calPiece={cp} />
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CalendarView({ workspaceId, campaignId }) {
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [weekStart, setWeekStart] = useState(() => getWeekStart(today));
  const [calData, setCalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [calViewMode, setCalViewMode] = useState(
    () => localStorage.getItem(CAL_VIEW_MODE_KEY) || "month"
  );

  const handleCalViewMode = (mode) => {
    setCalViewMode(mode);
    localStorage.setItem(CAL_VIEW_MODE_KEY, mode);
  };

  const load = useCallback(async () => {
    if (!workspaceId || !campaignId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getCalendar(workspaceId, campaignId);
      setCalData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, campaignId]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  const prevMonth = () => {
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const nextMonth = () => {
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const prevWeek = () => {
    setWeekStart((ws) => {
      const d = new Date(ws);
      d.setDate(d.getDate() - 7);
      return d;
    });
  };

  const nextWeek = () => {
    setWeekStart((ws) => {
      const d = new Date(ws);
      d.setDate(d.getDate() + 7);
      return d;
    });
  };

  // Build a map from ISO date string → array of CalendarPiece
  const piecesByDate = {};
  if (calData?.scheduled) {
    for (const group of calData.scheduled) {
      piecesByDate[group.date] = group.pieces;
    }
  }

  const grid = buildCalendarGrid(viewYear, viewMonth);
  const todayISO = toISODate(today);

  // Compute week range label
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);
  const weekRangeLabel = `${formatWeekDay(weekStart, today.getFullYear())} – ${formatWeekDay(weekEnd, today.getFullYear())}`;

  if (error) {
    return (
      <div className="card stage-error-card">
        <h2>📅 Calendar</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Failed to load calendar</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card cal-wrapper">
      <div className="cal-header">
        <h2>📅 Calendar</h2>
        <div className="cal-header-controls">
          {calViewMode === "month" ? (
            <div className="cal-nav">
              <button className="cal-nav-btn" onClick={prevMonth} aria-label="Previous month">‹</button>
              <span className="cal-month-label">{MONTH_NAMES[viewMonth]} {viewYear}</span>
              <button className="cal-nav-btn" onClick={nextMonth} aria-label="Next month">›</button>
            </div>
          ) : (
            <div className="cal-nav">
              <button className="cal-nav-btn" onClick={prevWeek} aria-label="Previous week">‹</button>
              <span className="cal-month-label">{weekRangeLabel}</span>
              <button className="cal-nav-btn" onClick={nextWeek} aria-label="Next week">›</button>
            </div>
          )}
          <div className="view-toggle" role="group" aria-label="Calendar view">
            <button
              className={`view-toggle-btn${calViewMode === "month" ? " active" : ""}`}
              onClick={() => handleCalViewMode("month")}
              title="Monthly view"
            >
              Month
            </button>
            <button
              className={`view-toggle-btn${calViewMode === "week" ? " active" : ""}`}
              onClick={() => handleCalViewMode("week")}
              title="Weekly view"
            >
              Week
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loading"><span className="spinner" /> Loading calendar…</div>
      ) : calViewMode === "month" ? (
        <div className="cal-grid-container">
          {/* Weekday headers */}
          <div className="cal-grid">
            {WEEKDAY_LABELS.map((day) => (
              <div key={day} className="cal-weekday-header">{day}</div>
            ))}

            {/* Day cells */}
            {grid.map((date, idx) => {
              if (!date) {
                return <div key={`empty-${idx}`} className="cal-day cal-day--empty" />;
              }
              const iso = toISODate(date);
              const isToday = iso === todayISO;
              const pieces = piecesByDate[iso] || [];
              return (
                <div
                  key={iso}
                  className={`cal-day${isToday ? " cal-day--today" : ""}${pieces.length > 0 ? " cal-day--has-pieces" : ""}`}
                >
                  <span className={`cal-day-number${isToday ? " cal-day-number--today" : ""}`}>
                    {date.getDate()}
                  </span>
                  <div className="cal-day-pieces">
                    {pieces.map((cp) => (
                      <ContentPieceCard key={cp.piece_index} calPiece={cp} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <WeeklyView weekStart={weekStart} piecesByDate={piecesByDate} todayISO={todayISO} />
      )}

      {/* Legend */}
      {!loading && (
        <div className="cal-legend">
          {Object.entries(CHANNEL_COLORS).map(([channel, colors]) => (
            <span
              key={channel}
              className="cal-legend-item"
              style={{ background: colors.bg, color: colors.text }}
            >
              {getChannelIcon(channel)} {channel.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
