import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getWorkspaceCalendar } from "../api";

// \u2500\u2500\u2500 Shared constants \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

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

const CONTENT_TYPE_ICONS = {
  headline:      "\u270D\uFE0F",
  body_copy:     "\uD83D\uDCC4",
  cta:           "\uD83C\uDFAF",
  social_post:   "\uD83D\uDCF1",
  email_subject: "\u2709\uFE0F",
  image:         "\uD83D\uDDBC\uFE0F",
};

const MONTH_DAY_MAX_VISIBLE = 3;

// \u2500\u2500\u2500 Utility helpers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function toMonthParam(year, month) {
  return `${year}-${String(month + 1).padStart(2, "0")}`;
}

function buildCalendarGrid(year, month) {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function getChannelColor(channel) {
  return CHANNEL_COLORS[channel] || { bg: "var(--cal-ch-default-bg)", text: "var(--cal-ch-default-text)" };
}

function getContentIcon(contentType) {
  return CONTENT_TYPE_ICONS[contentType] || "\uD83D\uDCCB";
}

function truncate(str, max = 50) {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "\u2026" : str;
}

// \u2500\u2500\u2500 WorkspacePieceCard (compact single-line pill) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
function WorkspacePieceCard({ wsPiece }) {
  const { piece, campaign_name } = wsPiece;
  const colors = getChannelColor(piece.channel);
  return (
    <div
      className="cal-piece-card cal-piece-card--compact"
      style={{ background: colors.bg, color: colors.text }}
      title={`${campaign_name}: ${piece.content}`}
    >
      <span className="cal-piece-icon" aria-hidden="true">
        {getContentIcon(piece.content_type)}
      </span>
      <span className="cal-piece-text">{truncate(piece.content, 30)}</span>
      {piece.channel && (
        <span className="cal-piece-channel-badge cal-piece-channel-badge--compact" style={{ background: colors.bg, color: colors.text }}>
          {piece.channel.replace(/_/g, " ")}
        </span>
      )}
    </div>
  );
}

// \u2500\u2500\u2500 Month day cell with +N more overflow \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

function WsMonthDayCell({ date, pieces, isToday }) {
  const [expanded, setExpanded] = useState(false);
  const overflow = pieces.length > MONTH_DAY_MAX_VISIBLE && !expanded;
  const visible = overflow ? pieces.slice(0, MONTH_DAY_MAX_VISIBLE) : pieces;
  const hiddenCount = pieces.length - MONTH_DAY_MAX_VISIBLE;

  return (
    <div
      className={`cal-day cal-day--month-compact${isToday ? " cal-day--today" : ""}${pieces.length > 0 ? " cal-day--has-pieces" : ""}`}
    >
      <div className={`cal-day-number${isToday ? " cal-day-number--today" : ""}`}>
        {date.getDate()}
      </div>
      <div className="cal-day-pieces">
        {visible.map((wsPiece, i) => (
          <WorkspacePieceCard key={`${wsPiece.campaign_id}-${wsPiece.piece_index}-${i}`} wsPiece={wsPiece} />
        ))}
        {overflow && (
          <button
            type="button"
            className="cal-day-more-btn"
            onClick={() => setExpanded(true)}
          >
            +{hiddenCount} more
          </button>
        )}
        {expanded && pieces.length > MONTH_DAY_MAX_VISIBLE && (
          <button
            type="button"
            className="cal-day-more-btn"
            onClick={() => setExpanded(false)}
          >
            show less
          </button>
        )}
      </div>
    </div>
  );
}

// \u2500\u2500\u2500 WorkspaceCalendar page \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
export default function WorkspaceCalendar() {
  const { id: workspaceId } = useParams();
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [calData, setCalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getWorkspaceCalendar(workspaceId, toMonthParam(viewYear, viewMonth));
      setCalData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, viewYear, viewMonth]);

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

  // Build date \u2192 pieces map from the API response
  const piecesByDate = {};
  if (calData?.scheduled) {
    for (const group of calData.scheduled) {
      piecesByDate[group.date] = group.pieces;
    }
  }

  const grid = buildCalendarGrid(viewYear, viewMonth);
  const todayISO = toISODate(today);

  if (error) {
    return (
      <div className="card stage-error-card">
        <h2>\uD83D\uDCC5 Workspace Calendar</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">\u26A0\uFE0F</span>
          <div>
            <p><strong>Failed to load calendar</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
        <Link to={`/workspaces/${workspaceId}`} className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          \u2190 Back to Workspace
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: "0.75rem" }}>
        <Link to={`/workspaces/${workspaceId}`} className="btn btn-outline">
          \u2190 Back to Workspace
        </Link>
      </div>

      <div className="card cal-wrapper">
        <div className="cal-header">
          <h2>\uD83D\uDCC5 Workspace Calendar</h2>
          <div className="cal-header-controls">
            <div className="cal-nav">
              <button className="cal-nav-btn" onClick={prevMonth} aria-label="Previous month">\u2039</button>
              <span className="cal-month-label">{MONTH_NAMES[viewMonth]} {viewYear}</span>
              <button className="cal-nav-btn" onClick={nextMonth} aria-label="Next month">\u203A</button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="loading"><span className="spinner" /> Loading calendar\u2026</div>
        ) : (
          <div className="cal-body">
            <div className="cal-main">
              <div className="cal-grid-container">
                <div className="cal-grid cal-grid--month-compact">
                  {WEEKDAY_LABELS.map((day) => (
                    <div key={day} className="cal-weekday-header">{day}</div>
                  ))}

                  {grid.map((date, idx) => {
                    if (!date) {
                      return <div key={`empty-${idx}`} className="cal-day cal-day--empty" />;
                    }
                    const iso = toISODate(date);
                    const isToday = iso === todayISO;
                    const pieces = piecesByDate[iso] || [];
                    return (
                      <WsMonthDayCell
                        key={iso}
                        date={date}
                        pieces={pieces}
                        isToday={isToday}
                      />
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
