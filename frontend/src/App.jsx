import { Routes, Route, NavLink } from "react-router-dom";
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import Dashboard from "./pages/Dashboard.jsx";
import NewCampaign from "./pages/NewCampaign.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import useWebSocket from "./hooks/useWebSocket.js";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { loginRequest } from "./authConfig.js";

/**
 * When VITE_AZURE_CLIENT_ID is set we enforce authentication;
 * otherwise the app runs in open / local-dev mode.
 */
const authEnabled = !!import.meta.env.VITE_AZURE_CLIENT_ID;

function LoginPage() {
  const { instance } = useMsal();

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span role="img" aria-label="rocket">🚀</span> Campaign Builder
        </h1>
      </header>
      <main className="app-main" style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <div className="card" style={{ textAlign: "center", maxWidth: 420 }}>
          <h2>Welcome</h2>
          <p style={{ color: "var(--color-text-muted)", marginBottom: "1.5rem" }}>
            Sign in with your Microsoft account to continue.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => instance.loginRedirect(loginRequest)}
          >
            Sign in
          </button>
        </div>
      </main>
    </div>
  );
}

function AuthenticatedApp() {
  const { events, connected } = useWebSocket(null);
  const { instance, accounts } = useMsal();
  const activeAccount = accounts[0];

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
          <NavLink to="/new">+ New Campaign</NavLink>
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
          <Route path="/new" element={<NewCampaign />} />
          <Route path="/campaign/:id" element={<CampaignDetail />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  // When auth is not configured, render the app without any gate
  if (!authEnabled) {
    return <AuthenticatedApp />;
  }

  return (
    <>
      <AuthenticatedTemplate>
        <AuthenticatedApp />
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginPage />
      </UnauthenticatedTemplate>
    </>
  );
}
