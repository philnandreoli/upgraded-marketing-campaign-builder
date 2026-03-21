import { useEffect, useRef } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import Dashboard from "./pages/Dashboard.jsx";
import NewCampaign from "./pages/NewCampaign.jsx";
import CampaignDetail from "./pages/CampaignDetail.jsx";
import Admin from "./pages/Admin.jsx";
import UserSettings from "./pages/UserSettings.jsx";
import WorkspaceList from "./pages/WorkspaceList.jsx";
import WorkspaceDetail from "./pages/WorkspaceDetail.jsx";
import WorkspaceSettings from "./pages/WorkspaceSettings.jsx";
import useWebSocket from "./hooks/useWebSocket.js";
import AppNavbar from "./components/AppNavbar.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import NavigationProgress from "./components/NavigationProgress.jsx";
import { loginRequest } from "./authConfig.js";
import { UserProvider, useUser } from "./UserContext.jsx";
import { WorkspaceProvider } from "./WorkspaceContext.jsx";
import { ConfirmDialogProvider } from "./ConfirmDialogContext.jsx";
import { ToastProvider } from "./ToastContext.jsx";
import { NotificationProvider, useNotifications } from "./NotificationContext.jsx";

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
  const { isAdmin } = useUser();
  const { addEvent } = useNotifications();
  const lastIndexRef = useRef(0);

  // Feed new WebSocket events into the notification store
  useEffect(() => {
    if (events.length > lastIndexRef.current) {
      const newEvents = events.slice(lastIndexRef.current);
      newEvents.forEach(addEvent);
      lastIndexRef.current = events.length;
    }
  }, [events, addEvent]);

  return (
    <div className="app-shell">
      <NavigationProgress />
      <AppNavbar
        connected={connected}
        activeAccount={activeAccount}
        isAdmin={isAdmin}
        authEnabled={authEnabled}
        onLogout={() => instance.logoutRedirect()}
      />

      <main className="app-main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard events={events} />} />
            <Route path="/workspaces" element={<WorkspaceList />} />
            <Route path="/workspaces/:id" element={<WorkspaceDetail events={events} />} />
            <Route path="/workspaces/:id/settings" element={<RequireBuilder><WorkspaceSettings /></RequireBuilder>} />
            <Route path="/new" element={<RequireBuilder><NewCampaign /></RequireBuilder>} />
            <Route path="/workspaces/:workspaceId/campaigns/new" element={<RequireBuilder><NewCampaign /></RequireBuilder>} />
            <Route path="/workspaces/:workspaceId/campaigns/:campaignId/edit" element={<RequireBuilder><NewCampaign /></RequireBuilder>} />
            <Route path="/workspaces/:workspaceId/campaigns/:id" element={<CampaignDetail />} />
            <Route path="/campaign/:id" element={<CampaignDetail />} />
            <Route path="/settings" element={<UserSettings />} />
            <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
          </Routes>
        </ErrorBoundary>
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
          <ConfirmDialogProvider>
            <ToastProvider>
              <NotificationProvider>
                <AuthenticatedApp />
              </NotificationProvider>
            </ToastProvider>
          </ConfirmDialogProvider>
        </WorkspaceProvider>
      </UserProvider>
    );
  }

  return (
    <>
      <AuthenticatedTemplate>
        <UserProvider>
          <WorkspaceProvider>
            <ConfirmDialogProvider>
              <ToastProvider>
                <NotificationProvider>
                  <AuthenticatedApp />
                </NotificationProvider>
              </ToastProvider>
            </ConfirmDialogProvider>
          </WorkspaceProvider>
        </UserProvider>
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginPage />
      </UnauthenticatedTemplate>
    </>
  );
}
