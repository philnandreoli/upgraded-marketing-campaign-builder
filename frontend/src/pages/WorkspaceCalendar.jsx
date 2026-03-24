import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getWorkspaceCalendar } from "../api";

// ─── Shared constants ─────────────────────────────────────────────────────────

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
  headline:      "✍️",
  body_copy:     "📄",
  cta:           "🎯",
  social_post:   "📱",
  email_subject: "✉️",
  image:         "🖼️",
};

// ─── Utility helpers ──────────────────────────────────────────────────────────

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
  return CONTENT_TYPE_ICONS[contentType] || "📋";
}

function truncate(str, max = 50) {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "…" : str;
}

// ─── WorkspacePieceCard ───────────────────────────────────────────────────────

function WorkspacePieceCard({ wsPiece }) {
  const { piece, campaign_name } = wsPiece;
  const colors = getChannelColor(piece.channel);
  return (
    <div
      className="cal-piece-card"
      style={{ background: colors.bg, color: colors.text }}
      title={`${campaign_name}: ${piece.content}`}
    >
      <span className="cal-piece-icon" aria-hidden="true">
        {getContentIcon(piece.content_type)}
      </span>
      <span className="cal-piece-text">{truncate(piece.content, 45)}</span>
      <span
        className="ws-cal-campaign-badge"
        title={campaign_name}
      >
        {truncate(campaign_name, 20)}
      </span>
      {piece.channel && (
        <span className="cal-piece-channel-badge" style={{ background: colors.bg, color: colors.text }}>
          {piece.channel.replace(/_/g, " ")}
        </span>
      )}
    </div>
  );
}

// ─── WorkspaceCalendar page ───────────────────────────────────────────────────

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

  // Build date → pieces map from the API response
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
        <h2>📅 Workspace Calendar</h2>
        <div className="stage-error-message">
          <span className="stage-error-icon">⚠️</span>
          <div>
            <p><strong>Failed to load calendar</strong></p>
            <p className="stage-error-detail">{error}</p>
          </div>
        </div>
        <Link to={`/workspaces/${workspaceId}`} className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          ← Back to Workspace
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: "0.75rem" }}>
        <Link to={`/workspaces/${workspaceId}`} className="btn btn-outline">
          ← Back to Workspace
        </Link>
      </div>

      <div className="card cal-wrapper">
        <div className="cal-header">
          <h2>📅 Workspace Calendar</h2>
          <div className="cal-header-controls">
            <div className="cal-nav">
              <button className="cal-nav-btn" onClick={prevMonth} aria-label="Previous month">‹</button>
              <span className="cal-month-label">{MONTH_NAMES[viewMonth]} {viewYear}</span>
              <button className="cal-nav-btn" onClick={nextMonth} aria-label="Next month">›</button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="loading"><span className="spinner" /> Loading calendar…</div>
        ) : (
          <div className="cal-body">
            <div className="cal-main">
              <div className="cal-grid-container">
                <div className="cal-grid">
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
                      <div
                        key={iso}
                        className={`cal-day${isToday ? " cal-day--today" : ""}${pieces.length > 0 ? " cal-day--has-pieces" : ""}`}
                      >
                        <div className={`cal-day-number${isToday ? " cal-day-number--today" : ""}`}>
                          {date.getDate()}
                        </div>
                        <div className="cal-day-pieces">
                          {pieces.map((wsPiece, i) => (
                            <WorkspacePieceCard key={`${wsPiece.campaign_id}-${wsPiece.piece_index}-${i}`} wsPiece={wsPiece} />
                          ))}
                        </div>
                      </div>
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
