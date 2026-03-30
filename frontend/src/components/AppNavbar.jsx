import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import ThemeToggle from "./ThemeToggle.jsx";
import NotificationCenter from "./NotificationCenter.jsx";

/** Derive up-to-two initials from a display name or email. */
function getInitials(account) {
  if (!account) return "?";
  const name = account.name ?? account.username ?? "";
  const parts = name.trim().split(/\s+/).filter((p) => p.length > 0);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase() || "?";
}

/** Returns the className string for a NavLink in the navbar. */
function navLinkClass(isActive, extra = "") {
  const base = "navbar-link";
  const active = isActive ? "navbar-link--active" : "";
  return [base, active, extra].filter(Boolean).join(" ");
}

/** Geometric logomark — two overlapping squares forming a campaign funnel shape. */
function LogoMark() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className="navbar-logomark"
    >
      <rect x="2" y="2" width="14" height="14" rx="3" fill="#0D9488" opacity="0.9" />
      <rect x="12" y="12" width="14" height="14" rx="3" fill="#06B6D4" opacity="0.85" />
      <rect x="9" y="9" width="10" height="10" rx="2" fill="#0C0F1A" opacity="0.6" />
      <rect x="10" y="10" width="8" height="8" rx="1.5" fill="url(#logo-inner)" />
      <defs>
        <linearGradient id="logo-inner" x1="10" y1="10" x2="18" y2="18" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0D9488" />
          <stop offset="100%" stopColor="#06B6D4" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/**
 * AppNavbar — three-zone command bar.
 *
 * Props:
 *   connected    {boolean}  WebSocket live/offline status
 *   activeAccount {object}  MSAL account object (may be undefined)
 *   isAdmin      {boolean}
 *   authEnabled  {boolean}  Whether MSAL auth is configured
 *   onLogout     {Function} Callback to trigger logoutRedirect
 */
export default function AppNavbar({
  connected,
  activeAccount,
  isAdmin,
  authEnabled,
  onLogout,
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  const initials = getInitials(activeAccount);
  const displayName = activeAccount?.name ?? activeAccount?.username ?? "";

  return (
    <header className="navbar" role="banner">
      {/* ── Zone 1: Brand ─────────────────────────────────────── */}
      <div className="navbar-brand">
        <LogoMark />
        <span className="navbar-wordmark">Campaign Builder</span>
      </div>

      {/* ── Zone 2: Nav links (desktop) ───────────────────────── */}
      <nav className={`navbar-nav${menuOpen ? " navbar-nav--open" : ""}`} aria-label="Main navigation">
        <NavLink to="/" end className={({ isActive }) => navLinkClass(isActive)}>
          Workspaces
        </NavLink>
        <NavLink to="/templates" className={({ isActive }) => navLinkClass(isActive)}>
          Templates
        </NavLink>
        {isAdmin && (
          <NavLink to="/admin" className={({ isActive }) => navLinkClass(isActive)}>
            Admin
          </NavLink>
        )}
      </nav>

      {/* ── Zone 3: Actions ───────────────────────────────────── */}
      <div className="navbar-actions">
        <ThemeToggle />
        <NotificationCenter />

        {/* Vertical divider */}
        <span className="navbar-divider" aria-hidden="true" />

        {/* Status badge */}
        <span className={`navbar-status${connected ? " navbar-status--live" : " navbar-status--offline"}`}>
          <span className="navbar-status-dot" aria-hidden="true" />
          {connected ? "Live" : "Offline"}
        </span>

        {/* Settings — always visible for authenticated users */}
        <Link
          to="/settings"
          className="navbar-settings"
          aria-label="User settings"
          title="User settings"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
            <path d="M7.5 9.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" stroke="currentColor" strokeWidth="1.3" />
            <path d="M12.6 9.2l.7.4a.5.5 0 0 1 .2.7l-.8 1.4a.5.5 0 0 1-.7.2l-.7-.4a4.4 4.4 0 0 1-1 .6v.8a.5.5 0 0 1-.5.5H8.2a.5.5 0 0 1-.5-.5v-.8a4.5 4.5 0 0 1-1-.6l-.7.4a.5.5 0 0 1-.7-.2l-.8-1.4a.5.5 0 0 1 .2-.7l.7-.4a4.4 4.4 0 0 1 0-1.2l-.7-.4a.5.5 0 0 1-.2-.7l.8-1.4a.5.5 0 0 1 .7-.2l.7.4a4.4 4.4 0 0 1 1-.6V4a.5.5 0 0 1 .5-.5h1.6a.5.5 0 0 1 .5.5v.8a4.4 4.4 0 0 1 1 .6l.7-.4a.5.5 0 0 1 .7.2l.8 1.4a.5.5 0 0 1-.2.7l-.7.4a4.4 4.4 0 0 1 0 1.2Z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>

        {authEnabled && activeAccount && (
          <>
            <span className="navbar-divider" aria-hidden="true" />

            {/* User avatar + name */}
            <div className="navbar-user" title={displayName}>
              <span className="navbar-avatar" aria-hidden="true">{initials}</span>
              <span className="navbar-username">{displayName}</span>
            </div>

            {/* Sign out */}
            <button
              className="navbar-signout"
              onClick={onLogout}
              aria-label="Sign out"
              title="Sign out"
            >
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
                <path d="M6 2H2.5A1.5 1.5 0 0 0 1 3.5v8A1.5 1.5 0 0 0 2.5 13H6M10 10.5l3-3-3-3M13 7.5H5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </>
        )}

        {/* Mobile hamburger */}
        <button
          className={`navbar-hamburger${menuOpen ? " navbar-hamburger--open" : ""}`}
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
        >
          <span className="navbar-hamburger-bar" />
          <span className="navbar-hamburger-bar" />
          <span className="navbar-hamburger-bar" />
        </button>
      </div>
    </header>
  );
}
