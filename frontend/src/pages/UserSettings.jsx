import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMe } from "../api";

const TABS = [
  { key: "profile", label: "Profile" },
  { key: "preferences", label: "Preferences" },
  { key: "notifications", label: "Notifications" },
];

export default function UserSettings() {
  const [activeTab, setActiveTab] = useState("profile");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);
  // Success feedback container — used by future tab forms to display save confirmations.
  // eslint-disable-next-line no-unused-vars
  const [success, setSuccess] = useState(null);

  const loadUser = useCallback(() => {
    setLoading(true);
    setError(null);
    getMe()
      .then((data) => setUser(data))
      .catch((err) => setError(err.message ?? "Failed to load user settings."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getMe()
      .then((data) => setUser(data))
      .catch((err) => setError(err.message ?? "Failed to load user settings."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading" data-testid="settings-loading">
        <span className="spinner" /> Loading settings…
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" data-testid="settings-error">
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
        <button
          className="btn btn-outline"
          style={{ marginTop: "0.75rem" }}
          onClick={loadUser}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div style={{ marginBottom: "1rem", fontSize: "0.875rem", color: "var(--color-text-muted)" }}>
        <Link to="/">Dashboard</Link>
        {" / Settings"}
      </div>

      <div className="section-header">
        <h2>User Settings</h2>
      </div>

      {/* Success feedback */}
      {success && (
        <div
          className="card"
          data-testid="settings-success"
          style={{
            marginBottom: "1rem",
            color: "var(--color-success)",
            fontSize: "0.875rem",
          }}
        >
          {success}
        </div>
      )}

      {/* Tab navigation */}
      <div className="filter-tabs" role="tablist" aria-label="Settings tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`filter-tab${activeTab === tab.key ? " filter-tab--active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div className="card" style={{ marginTop: "1rem" }} role="tabpanel" aria-label={`${TABS.find((t) => t.key === activeTab)?.label} settings`}>
        {activeTab === "profile" && (
          <div data-testid="tab-profile">
            <h3>Profile</h3>
            <p style={{ color: "var(--color-text-muted)" }}>
              Signed in as <strong>{user?.display_name ?? user?.email ?? "—"}</strong>
            </p>
          </div>
        )}
        {activeTab === "preferences" && (
          <div data-testid="tab-preferences">
            <h3>Preferences</h3>
            <p style={{ color: "var(--color-text-muted)" }}>
              Preference settings will appear here.
            </p>
          </div>
        )}
        {activeTab === "notifications" && (
          <div data-testid="tab-notifications">
            <h3>Notifications</h3>
            <p style={{ color: "var(--color-text-muted)" }}>
              Notification settings will appear here.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
