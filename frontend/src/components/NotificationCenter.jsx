import { useState, useRef, useEffect } from "react";
import { useNotifications } from "../NotificationContext.jsx";

/**
 * Compute a human-friendly relative timestamp string.
 */
function relativeTime(isoString) {
  if (!isoString) return "";
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffSec = Math.floor((now - then) / 1000);

  if (diffSec < 10) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

/**
 * BellIcon — SVG bell used in the notification button.
 */
function BellIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M8 1.5C5.5 1.5 3.5 3.5 3.5 6v2.5L2 10.5v1h12v-1l-1.5-2V6c0-2.5-2-4.5-4.5-4.5zM6.5 13a1.5 1.5 0 003 0"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * NotificationCenter — bell icon with unread badge + dropdown panel.
 *
 * Renders in the AppNavbar actions zone. Clicking the bell opens a dropdown
 * showing the last 20 pipeline events with icon, stage, message, and
 * relative timestamp. Opening the dropdown marks all notifications as read.
 */
export default function NotificationCenter() {
  const { notifications, unreadCount, markAllRead, markRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const buttonRef = useRef(null);

  // Close the dropdown when clicking outside
  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  const togglePanel = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next) markAllRead();
      return next;
    });
  };

  return (
    <div className="notification-center">
      <button
        ref={buttonRef}
        className="notification-bell"
        onClick={togglePanel}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        aria-expanded={open}
        aria-haspopup="true"
        title="Notifications"
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span className="notification-badge" aria-hidden="true">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          className="notification-panel"
          role="region"
          aria-label="Notification history"
        >
          <div className="notification-panel-header">
            <span className="notification-panel-title">Notifications</span>
          </div>

          {notifications.length === 0 ? (
            <div className="notification-empty">No notifications yet</div>
          ) : (
            <ul className="notification-list">
              {notifications.map((n) => (
                <li
                  key={n.id}
                  className={`notification-item${n.read ? "" : " notification-item--unread"}`}
                  onClick={() => markRead(n.id)}
                >
                  <span className="notification-item-icon">{n.icon}</span>
                  <div className="notification-item-body">
                    {n.stage && (
                      <span className="notification-item-stage">{n.stage}</span>
                    )}
                    {n.message && (
                      <span className="notification-item-message">{n.message}</span>
                    )}
                  </div>
                  <time className="notification-item-time" dateTime={n.timestamp}>
                    {relativeTime(n.timestamp)}
                  </time>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
