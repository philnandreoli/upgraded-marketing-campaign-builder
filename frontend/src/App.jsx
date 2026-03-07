import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import Dashboard from "./pages/Dashboard.jsx";
import NewCampaign from "./pages/NewCampaign.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import Admin from "./pages/Admin.jsx";
import useWebSocket from "./hooks/useWebSocket.js";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { loginRequest } from "./authConfig.js";
import { UserProvider, useUser } from "./UserContext.jsx";
import { WorkspaceProvider } from "./WorkspaceContext.jsx";

/**
 * When VITE_AZURE_CLIENT_ID is set we enforce authentication;
 * otherwise the app runs in open / local-dev mode.
 */
const authEnabled = !!import.meta.env.VITE_AZURE_CLIENT_ID;

/** Route guard: redirects viewers to Dashboard when they try to access builder-only routes. */
function RequireBuilder({ children }) {
  const { isViewer } = useUser();
  return isViewer ? <Navigate to="/" replace /> : children;
}

/** Route guard: redirects non-admins to Dashboard. */
function RequireAdmin({ children }) {
  const { isAdmin } = useUser();
  return isAdmin ? children : <Navigate to="/" replace />;
}

function LoginPage() {
  const { instance } = useMsal();

  return (
    <div className="login-page">
      <div className="login-brand">
        <div className="login-brand-content">
          <div className="login-brand-icon" aria-hidden="true">🚀</div>
          <h1 className="login-title">Campaign Builder</h1>
          <p className="login-tagline">
            AI-powered marketing campaigns, from strategy to approval.
          </p>
          <div className="login-features">
            <div className="login-feature">🎯 Strategy Generation</div>
            <div className="login-feature">✍️ Content Creation</div>
            <div className="login-feature">📊 Analytics Planning</div>
          </div>
        </div>
      </div>

      <div className="login-form-area">
        <div className="login-card">
          <div className="login-card-logo" aria-hidden="true">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 23 23" width="40" height="40" aria-hidden="true">
              <rect x="1" y="1" width="10" height="10" fill="#F25022" />
              <rect x="12" y="1" width="10" height="10" fill="#7FBA00" />
              <rect x="1" y="12" width="10" height="10" fill="#00A4EF" />
              <rect x="12" y="12" width="10" height="10" fill="#FFB900" />
            </svg>
          </div>
          <h2 className="login-card-title">Welcome back</h2>
          <p className="login-card-subtitle">
            Sign in with your Microsoft account to continue building campaigns.
          </p>
          <button
            className="btn btn-primary btn-login"
            onClick={() => instance.loginRedirect(loginRequest)}
          >
            Sign in with Microsoft
          </button>
        </div>
      </div>
    </div>
  );
}

function AuthenticatedApp() {
  const { events, connected } = useWebSocket(null);
  const { instance, accounts } = useMsal();
  const activeAccount = accounts[0];
  const { isAdmin, isViewer } = useUser();

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span role="img" aria-label="rocket">🚀</span> Campaign Builder
        </h1>
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          {!isViewer && <NavLink to="/new">+ New Campaign</NavLink>}
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          <ThemeToggle />
          <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
            <span
              className={`ws-indicator ${connected ? "connected" : "disconnected"}`}
            />
            {connected ? "Live" : "Offline"}
          </span>
          {authEnabled && activeAccount && (
            <>
              <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)", marginLeft: "0.5rem" }}>
                {activeAccount.name ?? activeAccount.username}
              </span>
              <button
                className="btn btn-outline"
                style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", marginLeft: "0.25rem" }}
                onClick={() => instance.logoutRedirect()}
              >
                Sign out
              </button>
            </>
          )}
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard events={events} />} />
          <Route path="/new" element={<RequireBuilder><NewCampaign /></RequireBuilder>} />
          <Route path="/campaign/:id" element={<CampaignDetail />} />
          <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  // When auth is not configured, render the app without any gate
  if (!authEnabled) {
    return (
      <UserProvider>
        <WorkspaceProvider>
          <AuthenticatedApp />
        </WorkspaceProvider>
      </UserProvider>
    );
  }

  return (
    <>
      <AuthenticatedTemplate>
        <UserProvider>
          <WorkspaceProvider>
            <AuthenticatedApp />
          </WorkspaceProvider>
        </UserProvider>
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginPage />
      </UnauthenticatedTemplate>
    </>
  );
}
