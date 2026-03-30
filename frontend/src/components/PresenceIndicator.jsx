import { useState } from "react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract initials from display_name, e.g. "Alice Smith" → "AS".
 */
function getInitials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

// ---------------------------------------------------------------------------
// PresenceIndicator
// ---------------------------------------------------------------------------

const MAX_VISIBLE = 3;

export default function PresenceIndicator({ users = [] }) {
  const [hoveredUser, setHoveredUser] = useState(null);

  if (users.length === 0) return null;

  const visible = users.slice(0, MAX_VISIBLE);
  const overflow = users.length - MAX_VISIBLE;

  return (
    <div className="presence-indicator" data-testid="presence-indicator" aria-label={`${users.length} user${users.length !== 1 ? "s" : ""} viewing`}>
      {visible.map((user) => (
        <span
          key={user.id}
          className="presence-indicator-avatar"
          onMouseEnter={() => setHoveredUser(user.id)}
          onMouseLeave={() => setHoveredUser(null)}
          title={user.display_name || "User"}
          aria-label={user.display_name || "User"}
        >
          {user.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.display_name || "User"}
              className="presence-indicator-img"
            />
          ) : (
            <span className="presence-indicator-initials">{getInitials(user.display_name)}</span>
          )}
          {hoveredUser === user.id && (
            <span className="presence-indicator-tooltip" role="tooltip">
              {user.display_name || "User"}
            </span>
          )}
        </span>
      ))}
      {overflow > 0 && (
        <span className="presence-indicator-overflow" title={`${overflow} more user${overflow !== 1 ? "s" : ""}`}>
          +{overflow}
        </span>
      )}
    </div>
  );
}
