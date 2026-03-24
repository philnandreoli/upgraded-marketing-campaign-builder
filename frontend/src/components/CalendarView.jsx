import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCalendar, schedulePiece } from "../api";
import { useToast } from "../ToastContext";
import DatePicker from "./DatePicker";

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
const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CAL_VIEW_MODE_KEY = "cal_view_mode";
const CAL_SIDEBAR_COLLAPSED_KEY = "cal_sidebar_collapsed";

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
  const label = `${MONTH_ABBR[date.getMonth()]} ${date.getDate()}`;
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

// Format an integer hour (24h) as a readable label, e.g. 12 → "12 PM", 9 → "9 AM", 14 → "2 PM"
function formatHour(h) {
  if (h === 12) return "12 PM";
  return h < 12 ? `${h} AM` : `${h - 12} PM`;
}

function ContentPieceCard({ calPiece, isDraggable = false, isDragging = false, onDragStart, onDragEnd }) {
  const { piece } = calPiece;
  const colors = getChannelColor(piece.channel);
  return (
    <div
      className={`cal-piece-card${isDragging ? " cal-piece-card--dragging" : ""}${isDraggable ? " cal-piece-card--draggable" : ""}`}
      style={{ background: colors.bg, color: colors.text }}
      title={piece.content}
      draggable={isDraggable}
      onDragStart={isDraggable ? onDragStart : undefined}
      onDragEnd={isDraggable ? onDragEnd : undefined}
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
function WeeklyView({ weekStart, piecesByDate, todayISO, isViewer, draggingIndex, dragOverDate, onDragStart, onDragEnd, onDragOver, onDragLeave, onDrop }) {
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
          <div
            key={iso}
            className={`cal-week-allday-cell${dragOverDate === iso ? " cal-week-allday-cell--drag-over" : ""}`}
            onDragOver={!isViewer ? (e) => onDragOver(e, iso) : undefined}
            onDragLeave={!isViewer ? onDragLeave : undefined}
            onDrop={!isViewer ? (e) => onDrop(e, iso) : undefined}
          >
            {allDay.map((cp) => (
              <ContentPieceCard
                key={cp.piece_index}
                calPiece={cp}
                isDraggable={!isViewer}
                isDragging={draggingIndex === cp.piece_index}
                onDragStart={(e) => onDragStart(e, cp.piece_index, iso)}
                onDragEnd={onDragEnd}
              />
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
              {formatHour(h)}
            </div>
          ))}
        </div>

        {/* Day columns */}
        {dayData.map(({ iso, timed }) => {
          const isToday = iso === todayISO;
          return (
            <div
              key={iso}
              className={`cal-week-day-col${isToday ? " cal-week-day-col--today" : ""}${dragOverDate === iso ? " cal-week-day-col--drag-over" : ""}`}
              onDragOver={!isViewer ? (e) => onDragOver(e, iso) : undefined}
              onDragLeave={!isViewer ? onDragLeave : undefined}
              onDrop={!isViewer ? (e) => onDrop(e, iso) : undefined}
            >
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
                const clampedTop = Math.max(0, Math.min(topFrac, HOUR_END - HOUR_START));
                return (
                  <div
                    key={cp.piece_index}
                    className="cal-week-timed-piece"
                    style={{ top: `${clampedTop * slotHeight}px` }}
                  >
                    <ContentPieceCard
                      calPiece={cp}
                      isDraggable={!isViewer}
                      isDragging={draggingIndex === cp.piece_index}
                      onDragStart={(e) => onDragStart(e, cp.piece_index, iso)}
                      onDragEnd={onDragEnd}
                    />
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

function UnscheduledSidebar({ unscheduled, isViewer, onSchedule, collapsed, onToggle, draggingIndex, onDragStart, onDragEnd }) {
  const [schedulingPieceIndex, setSchedulingPieceIndex] = useState(null);
  const [scheduleError, setScheduleError] = useState(null);

  const handleScheduleClick = (pieceIndex) => {
    setScheduleError(null);
    setSchedulingPieceIndex(pieceIndex);
  };

  const handleDateChange = async (e, pieceIndex) => {
    const dateStr = e.target.value;
    if (!dateStr) return;
    setSchedulingPieceIndex(null);
    setScheduleError(null);
    try {
      await onSchedule(pieceIndex, dateStr);
    } catch {
      setScheduleError("Failed to schedule. Please try again.");
    }
  };

  const count = unscheduled.length;

  return (
    <div className="cal-unscheduled-sidebar">
      <button
        type="button"
        className="cal-sidebar-header"
        onClick={onToggle}
        aria-expanded={!collapsed}
      >
        <span className="cal-sidebar-title">
          Unscheduled
          <span className="cal-sidebar-count-badge" aria-label={`${count} unscheduled`}>
            {count}
          </span>
        </span>
        <span className="cal-sidebar-chevron" aria-hidden="true">
          {collapsed ? "›" : "⌄"}
        </span>
      </button>

      {!collapsed && (
        <div className="cal-sidebar-body">
          {scheduleError && (
            <p className="cal-sidebar-error">{scheduleError}</p>
          )}
          {count === 0 ? (
            <p className="cal-sidebar-empty">All content is scheduled!</p>
          ) : (
            unscheduled.map((calPiece) => {
              const { piece, piece_index } = calPiece;
              const colors = getChannelColor(piece.channel);
              const isScheduling = schedulingPieceIndex === piece_index;
              return (
                <div
                  key={piece_index}
                  className={`cal-unscheduled-card${draggingIndex === piece_index ? " cal-unscheduled-card--dragging" : ""}${!isViewer ? " cal-unscheduled-card--draggable" : ""}`}
                  draggable={!isViewer}
                  onDragStart={!isViewer ? (e) => onDragStart(e, piece_index, null) : undefined}
                  onDragEnd={!isViewer ? onDragEnd : undefined}
                >
                  <div className="cal-unscheduled-card-meta">
                    <span className="cal-piece-icon" aria-hidden="true">
                      {getContentIcon(piece.content_type)}
                    </span>
                    {piece.channel && (
                      <span
                        className="cal-piece-channel-badge"
                        style={{ background: colors.bg, color: colors.text }}
                      >
                        {getChannelIcon(piece.channel)} {piece.channel.replace(/_/g, " ")}
                      </span>
                    )}
                  </div>
                  <p className="cal-unscheduled-card-content" title={piece.content}>
                    {truncate(piece.content, 80)}
                  </p>
                  {!isViewer && (
                    isScheduling ? (
                      <div className="cal-unscheduled-datepicker">
                        <DatePicker
                          value=""
                          onChange={(e) => handleDateChange(e, piece_index)}
                          min={new Date().toISOString().slice(0, 10)}
                          placeholder="Pick a date"
                        />
                        <button
                          type="button"
                          className="cal-sidebar-cancel-btn"
                          onClick={() => setSchedulingPieceIndex(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="cal-schedule-btn"
                        onClick={() => handleScheduleClick(piece_index)}
                      >
                        Schedule
                      </button>
                    )
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export default function CalendarView({ workspaceId, campaignId, isViewer = false, startDate }) {
  const today = new Date();

  // Anchor the initial view to the campaign start date (or today if in the past/absent)
  const initialDate = useMemo(() => {
    const now = new Date();
    if (startDate) {
      const sd = new Date(startDate + "T00:00:00");
      return sd >= now ? sd : now;
    }
    return now;
  }, [startDate]);

  const [viewYear, setViewYear] = useState(initialDate.getFullYear());
  const [viewMonth, setViewMonth] = useState(initialDate.getMonth());
  const [weekStart, setWeekStart] = useState(() => getWeekStart(initialDate));
  const [calData, setCalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [calViewMode, setCalViewMode] = useState(() => {
    const stored = localStorage.getItem(CAL_VIEW_MODE_KEY);
    return stored === "week" || stored === "month" ? stored : "week";
  });

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem(CAL_SIDEBAR_COLLAPSED_KEY) === "true";
  });

  // Drag-and-drop state
  const dragRef = useRef(null); // { pieceIndex: number, fromDate: string|null }
  const [dragOverDate, setDragOverDate] = useState(null);
  const [draggingIndex, setDraggingIndex] = useState(null);

  const { addToast } = useToast();

  const handleCalViewMode = (mode) => {
    setCalViewMode(mode);
    localStorage.setItem(CAL_VIEW_MODE_KEY, mode);
  };

  const handleSidebarToggle = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(CAL_SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
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

  const handleSchedulePiece = useCallback(async (pieceIndex, dateStr) => {
    await schedulePiece(workspaceId, campaignId, pieceIndex, { scheduledDate: dateStr });
    load();
  }, [workspaceId, campaignId, load]);

  // ── Drag-and-drop handlers ──────────────────────────────────────────────
  const handleDragStart = useCallback((e, pieceIndex, fromDate) => {
    dragRef.current = { pieceIndex, fromDate };
    setDraggingIndex(pieceIndex);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggingIndex(null);
    setDragOverDate(null);
  }, []);

  const handleDragOver = useCallback((e, isoDate) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    setDragOverDate(isoDate);
  }, []);

  const handleDragLeave = useCallback((e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setDragOverDate(null);
    }
  }, []);

  const handleDrop = useCallback(async (e, isoDate) => {
    e.preventDefault();
    const drag = dragRef.current;
    if (!drag) return;

    const { pieceIndex, fromDate } = drag;
    dragRef.current = null;
    setDraggingIndex(null);
    setDragOverDate(null);

    // No-op: dropping on the same date
    if (fromDate === isoDate) return;

    // Find the piece being moved and compute the optimistic state
    let movingPiece = null;
    const optimisticScheduled = (calData?.scheduled || []).reduce((acc, group) => {
      if (group.date === fromDate) {
        const filtered = group.pieces.filter((cp) => {
          if (cp.piece_index === pieceIndex) { movingPiece = cp; return false; }
          return true;
        });
        if (filtered.length > 0) acc.push({ ...group, pieces: filtered });
      } else {
        acc.push(group);
      }
      return acc;
    }, []);

    let optimisticUnscheduled = calData?.unscheduled || [];
    if (!movingPiece) {
      optimisticUnscheduled = optimisticUnscheduled.filter((cp) => {
        if (cp.piece_index === pieceIndex) { movingPiece = cp; return false; }
        return true;
      });
    }

    if (!movingPiece) return;

    const movedPiece = { ...movingPiece, piece: { ...movingPiece.piece, scheduled_date: isoDate } };
    const targetGroup = optimisticScheduled.find((g) => g.date === isoDate);
    if (targetGroup) {
      const idx = optimisticScheduled.indexOf(targetGroup);
      optimisticScheduled[idx] = { ...targetGroup, pieces: [...targetGroup.pieces, movedPiece] };
    } else {
      optimisticScheduled.push({ date: isoDate, pieces: [movedPiece] });
      optimisticScheduled.sort((a, b) => a.date.localeCompare(b.date));
    }

    const snapshot = calData;
    setCalData({ ...calData, scheduled: optimisticScheduled, unscheduled: optimisticUnscheduled });

    try {
      await schedulePiece(workspaceId, campaignId, pieceIndex, { scheduledDate: isoDate });
      addToast({ type: "success", stage: "Scheduled", message: "Content piece rescheduled." });
    } catch {
      setCalData(snapshot);
      addToast({ type: "error", stage: "Error", message: "Failed to reschedule. Please try again." });
    }
  }, [calData, workspaceId, campaignId, addToast]);
  // ────────────────────────────────────────────────────────────────────────

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
      ) : (
        <div className="cal-body">
          <div className="cal-main">
            {calViewMode === "month" ? (
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
                        className={`cal-day${isToday ? " cal-day--today" : ""}${pieces.length > 0 ? " cal-day--has-pieces" : ""}${dragOverDate === iso ? " cal-day--drag-over" : ""}`}
                        onDragOver={!isViewer ? (e) => handleDragOver(e, iso) : undefined}
                        onDragLeave={!isViewer ? handleDragLeave : undefined}
                        onDrop={!isViewer ? (e) => handleDrop(e, iso) : undefined}
                      >
                        <span className={`cal-day-number${isToday ? " cal-day-number--today" : ""}`}>
                          {date.getDate()}
                        </span>
                        <div className="cal-day-pieces">
                          {pieces.map((cp) => (
                            <ContentPieceCard
                              key={cp.piece_index}
                              calPiece={cp}
                              isDraggable={!isViewer}
                              isDragging={draggingIndex === cp.piece_index}
                              onDragStart={(e) => handleDragStart(e, cp.piece_index, iso)}
                              onDragEnd={handleDragEnd}
                            />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <WeeklyView
                weekStart={weekStart}
                piecesByDate={piecesByDate}
                todayISO={todayISO}
                isViewer={isViewer}
                draggingIndex={draggingIndex}
                dragOverDate={dragOverDate}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              />
            )}
          </div>

          <UnscheduledSidebar
            unscheduled={calData?.unscheduled || []}
            isViewer={isViewer}
            onSchedule={handleSchedulePiece}
            collapsed={sidebarCollapsed}
            onToggle={handleSidebarToggle}
            draggingIndex={draggingIndex}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          />
        </div>
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
