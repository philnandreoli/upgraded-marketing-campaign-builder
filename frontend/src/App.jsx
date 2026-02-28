import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import {
  useIsAuthenticated,
  useMsal,
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
} from "@azure/msal-react";
import Dashboard from "./pages/Dashboard.jsx";
import NewCampaign from "./pages/NewCampaign.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import useWebSocket from "./hooks/useWebSocket.js";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { loginRequest } from "./authConfig.js";

const AUTH_ENABLED = import.meta.env.VITE_AZURE_CLIENT_ID ? true : false;

function AuthButton() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  const handleLogin = () =>
    instance.loginRedirect(loginRequest).catch(console.error);

  const handleLogout = () =>
    instance.logoutRedirect({ postLogoutRedirectUri: window.location.origin });

  if (isAuthenticated) {
    const name = accounts[0]?.name ?? accounts[0]?.username ?? "User";
    return (
      <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
          {name}
        </span>
        <button className="btn btn-outline" style={{ padding: "0.3rem 0.7rem", fontSize: "0.8rem" }} onClick={handleLogout}>
          Sign out
        </button>
      </span>
    );
  }

  return (
    <button className="btn btn-primary" style={{ padding: "0.3rem 0.7rem", fontSize: "0.8rem" }} onClick={handleLogin}>
      Sign in
    </button>
  );
}

function AppShell() {
  const { events, connected } = useWebSocket(null);

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
          {AUTH_ENABLED && <AuthButton />}
          <span style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
            <span
              className={`ws-indicator ${connected ? "connected" : "disconnected"}`}
            />
            {connected ? "Live" : "Offline"}
          </span>
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

function LoginPrompt() {
  const { instance } = useMsal();
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "100vh", gap: "1rem" }}>
      <h1><span role="img" aria-label="rocket">🚀</span> Campaign Builder</h1>
      <p style={{ color: "var(--color-text-dim)" }}>Sign in to create and manage your marketing campaigns.</p>
      <button
        className="btn btn-primary"
        onClick={() => instance.loginRedirect(loginRequest).catch(console.error)}
      >
        Sign in with Microsoft
      </button>
    </div>
  );
}

export default function App() {
  if (!AUTH_ENABLED) {
    return <AppShell />;
  }

  return (
    <>
      <AuthenticatedTemplate>
        <AppShell />
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginPrompt />
      </UnauthenticatedTemplate>
    </>
  );
}
