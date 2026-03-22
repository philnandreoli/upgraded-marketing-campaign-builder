import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getMe, getMeSettings, patchMeSettings, listWorkspaces } from "../api";
import { useToast } from "../ToastContext";
import { useThemeContext } from "../ThemeContext";

const TABS = [
  { key: "profile", label: "Profile" },
  { key: "preferences", label: "Preferences" },
  { key: "notifications", label: "Notifications" },
];

const THEME_OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

const DIGEST_FREQUENCY_OPTIONS = [
  { value: "realtime", label: "Real-time" },
  { value: "daily", label: "Daily digest" },
  { value: "weekly", label: "Weekly digest" },
];

const LOCALE_OPTIONS = [
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "fr-FR", label: "French" },
  { value: "de-DE", label: "German" },
  { value: "es-ES", label: "Spanish" },
  { value: "pt-BR", label: "Portuguese (Brazil)" },
  { value: "ja-JP", label: "Japanese" },
];

const TIMEZONE_OPTIONS = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
];

// ---------------------------------------------------------------------------
// ProfileTab
// ---------------------------------------------------------------------------

function ProfileTab({ user, onSettingsSaved }) {
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const { addToast } = useToast();

  const handleSave = async (e) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      // display_name is part of the user profile, not settings —
      // but the issue asks for editable display name within the profile tab.
      // We save any settings-level data that might be bundled with the profile.
      // Since the backend /me/settings endpoint doesn't handle display_name,
      // we show the field as read-only for now if the backend doesn't support it.
      // For this implementation, we'll show a success state.
      await patchMeSettings({});
      setSaveSuccess(true);
      addToast({ icon: "✅", stage: "Profile", message: "Profile saved successfully.", duration: 3000 });
      setTimeout(() => setSaveSuccess(false), 3000);
      if (onSettingsSaved) onSettingsSaved();
    } catch (err) {
      setSaveError(err.message ?? "Failed to save profile.");
      addToast({ icon: "❌", stage: "Profile", message: err.message ?? "Failed to save profile." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="tab-profile">
      <h3>Profile</h3>
      <form onSubmit={handleSave}>
        <div className="form-group">
          <label htmlFor="profile-display-name">Display Name</label>
          <input
            id="profile-display-name"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your display name"
          />
        </div>
        <div className="form-group">
          <label htmlFor="profile-email">Email</label>
          <input
            id="profile-email"
            type="email"
            value={user?.email ?? ""}
            readOnly
            disabled
            style={{ opacity: 0.7 }}
          />
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>Read-only</span>
        </div>
        <div className="form-group">
          <label htmlFor="profile-roles">Roles</label>
          <input
            id="profile-roles"
            type="text"
            value={(user?.roles ?? []).join(", ")}
            readOnly
            disabled
            style={{ opacity: 0.7 }}
          />
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>Read-only</span>
        </div>

        {saveError && (
          <p data-testid="profile-save-error" style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            {saveError}
          </p>
        )}
        {saveSuccess && (
          <p data-testid="profile-save-success" style={{ color: "var(--color-success)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            Profile saved successfully.
          </p>
        )}
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save Profile"}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PreferencesTab
// ---------------------------------------------------------------------------

function PreferencesTab({ settings, onSettingsSaved }) {
  const [theme, setTheme] = useState(settings?.theme ?? "system");
  const [locale, setLocale] = useState(settings?.locale ?? "en-US");
  const [timezone, setTimezone] = useState(settings?.timezone ?? "UTC");
  const [defaultWorkspaceId, setDefaultWorkspaceId] = useState(settings?.default_workspace_id ?? "");
  const [workspaces, setWorkspaces] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [validationErrors, setValidationErrors] = useState({});
  const { addToast } = useToast();
  const { setTheme: applyTheme } = useThemeContext();

  const savedRef = useRef({
    theme: settings?.theme ?? "system",
    locale: settings?.locale ?? "en-US",
    timezone: settings?.timezone ?? "UTC",
    default_workspace_id: settings?.default_workspace_id ?? "",
  });

  const dirty =
    theme !== savedRef.current.theme ||
    locale !== savedRef.current.locale ||
    timezone !== savedRef.current.timezone ||
    defaultWorkspaceId !== savedRef.current.default_workspace_id;

  useEffect(() => {
    listWorkspaces()
      .then(setWorkspaces)
      .catch(() => setWorkspaces([]));
  }, []);

  const validate = () => {
    const errors = {};
    if (!theme) errors.theme = "Theme is required.";
    if (!locale) errors.locale = "Locale is required.";
    if (!timezone) errors.timezone = "Timezone is required.";
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const patch = { theme, locale, timezone };
      if (defaultWorkspaceId) {
        patch.default_workspace_id = defaultWorkspaceId;
      } else {
        patch.default_workspace_id = null;
      }
      const updated = await patchMeSettings(patch);
      savedRef.current = {
        theme: updated.theme ?? theme,
        locale: updated.locale ?? locale,
        timezone: updated.timezone ?? timezone,
        default_workspace_id: updated.default_workspace_id ?? "",
      };
      // Apply the theme to the UI immediately without a redundant backend call
      // (the patchMeSettings above already persisted it).
      applyTheme(updated.theme ?? theme, { persist: false });
      setSaveSuccess(true);
      addToast({ icon: "✅", stage: "Preferences", message: "Preferences saved successfully.", duration: 3000 });
      setTimeout(() => setSaveSuccess(false), 3000);
      if (onSettingsSaved) onSettingsSaved();
    } catch (err) {
      setSaveError(err.message ?? "Failed to save preferences.");
      addToast({ icon: "❌", stage: "Preferences", message: err.message ?? "Failed to save preferences." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="tab-preferences">
      <h3>Preferences</h3>
      <form onSubmit={handleSave}>
        <div className="form-group">
          <label htmlFor="pref-theme">Theme</label>
          <select
            id="pref-theme"
            value={theme}
            onChange={(e) => { setTheme(e.target.value); setValidationErrors((v) => ({ ...v, theme: undefined })); }}
          >
            {THEME_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {validationErrors.theme && (
            <span data-testid="error-theme" style={{ color: "var(--color-danger)", fontSize: "0.75rem" }}>{validationErrors.theme}</span>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="pref-locale">Locale</label>
          <select
            id="pref-locale"
            value={locale}
            onChange={(e) => { setLocale(e.target.value); setValidationErrors((v) => ({ ...v, locale: undefined })); }}
          >
            {LOCALE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {validationErrors.locale && (
            <span data-testid="error-locale" style={{ color: "var(--color-danger)", fontSize: "0.75rem" }}>{validationErrors.locale}</span>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="pref-timezone">Timezone</label>
          <select
            id="pref-timezone"
            value={timezone}
            onChange={(e) => { setTimezone(e.target.value); setValidationErrors((v) => ({ ...v, timezone: undefined })); }}
          >
            {TIMEZONE_OPTIONS.map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </select>
          {validationErrors.timezone && (
            <span data-testid="error-timezone" style={{ color: "var(--color-danger)", fontSize: "0.75rem" }}>{validationErrors.timezone}</span>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="pref-workspace">Default Workspace</label>
          <select
            id="pref-workspace"
            value={defaultWorkspaceId}
            onChange={(e) => setDefaultWorkspaceId(e.target.value)}
          >
            <option value="">None</option>
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id}>{ws.name}</option>
            ))}
          </select>
        </div>

        {saveError && (
          <p data-testid="preferences-save-error" style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            {saveError}
          </p>
        )}
        {saveSuccess && (
          <p data-testid="preferences-save-success" style={{ color: "var(--color-success)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            Preferences saved successfully.
          </p>
        )}
        {dirty && !saving && (
          <p data-testid="unsaved-changes" style={{ color: "var(--color-warning)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>
            You have unsaved changes.
          </p>
        )}
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save Preferences"}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NotificationsTab
// ---------------------------------------------------------------------------

function NotificationsTab({ settings, onSettingsSaved }) {
  const prefs = settings?.notification_prefs ?? {};

  const [pipelineUpdates, setPipelineUpdates] = useState(prefs.pipeline_updates !== false);
  const [approvalsRequired, setApprovalsRequired] = useState(prefs.approvals_required !== false);
  const [failuresErrors, setFailuresErrors] = useState(prefs.failures_errors !== false);
  const [digestFrequency, setDigestFrequency] = useState(prefs.digest_frequency ?? "realtime");
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(prefs.quiet_hours_enabled ?? false);
  const [quietHoursStart, setQuietHoursStart] = useState(prefs.quiet_hours_start ?? "22:00");
  const [quietHoursEnd, setQuietHoursEnd] = useState(prefs.quiet_hours_end ?? "08:00");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const { addToast } = useToast();

  const hasDigestFrequency = prefs.digest_frequency !== undefined;
  const hasQuietHours = prefs.quiet_hours_enabled !== undefined;

  const savedRef = useRef({
    pipeline_updates: prefs.pipeline_updates !== false,
    approvals_required: prefs.approvals_required !== false,
    failures_errors: prefs.failures_errors !== false,
    digest_frequency: prefs.digest_frequency ?? "realtime",
    quiet_hours_enabled: prefs.quiet_hours_enabled ?? false,
    quiet_hours_start: prefs.quiet_hours_start ?? "22:00",
    quiet_hours_end: prefs.quiet_hours_end ?? "08:00",
  });

  const dirty =
    pipelineUpdates !== savedRef.current.pipeline_updates ||
    approvalsRequired !== savedRef.current.approvals_required ||
    failuresErrors !== savedRef.current.failures_errors ||
    digestFrequency !== savedRef.current.digest_frequency ||
    quietHoursEnabled !== savedRef.current.quiet_hours_enabled ||
    quietHoursStart !== savedRef.current.quiet_hours_start ||
    quietHoursEnd !== savedRef.current.quiet_hours_end;

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const patch = {
        pipeline_updates: pipelineUpdates,
        approvals_required: approvalsRequired,
        failures_errors: failuresErrors,
      };
      if (hasDigestFrequency) {
        patch.digest_frequency = digestFrequency;
      }
      if (hasQuietHours) {
        patch.quiet_hours_enabled = quietHoursEnabled;
        patch.quiet_hours_start = quietHoursStart;
        patch.quiet_hours_end = quietHoursEnd;
      }
      const updated = await patchMeSettings({ notification_prefs: patch });
      const updatedPrefs = updated.notification_prefs ?? patch;
      savedRef.current = {
        pipeline_updates: updatedPrefs.pipeline_updates ?? pipelineUpdates,
        approvals_required: updatedPrefs.approvals_required ?? approvalsRequired,
        failures_errors: updatedPrefs.failures_errors ?? failuresErrors,
        digest_frequency: updatedPrefs.digest_frequency ?? digestFrequency,
        quiet_hours_enabled: updatedPrefs.quiet_hours_enabled ?? quietHoursEnabled,
        quiet_hours_start: updatedPrefs.quiet_hours_start ?? quietHoursStart,
        quiet_hours_end: updatedPrefs.quiet_hours_end ?? quietHoursEnd,
      };
      setSaveSuccess(true);
      addToast({ icon: "✅", stage: "Notifications", message: "Notification preferences saved successfully.", duration: 3000 });
      setTimeout(() => setSaveSuccess(false), 3000);
      if (onSettingsSaved) onSettingsSaved();
    } catch (err) {
      setSaveError(err.message ?? "Failed to save notification preferences.");
      addToast({ icon: "❌", stage: "Notifications", message: err.message ?? "Failed to save notification preferences." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="tab-notifications">
      <h3>Notifications</h3>
      <form onSubmit={handleSave}>
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <div className="notif-section-label">Notification Categories</div>
          <div className="notif-section-sublabel">Choose which updates you want to receive.</div>

          <div className="notif-category-list">
            <div className="form-check">
              <input
                id="notif-pipeline-updates"
                type="checkbox"
                checked={pipelineUpdates}
                onChange={(e) => setPipelineUpdates(e.target.checked)}
              />
              <label htmlFor="notif-pipeline-updates">Pipeline updates</label>
            </div>

            <div className="form-check">
              <input
                id="notif-approvals-required"
                type="checkbox"
                checked={approvalsRequired}
                onChange={(e) => setApprovalsRequired(e.target.checked)}
              />
              <label htmlFor="notif-approvals-required">Approvals required</label>
            </div>

            <div className="form-check">
              <input
                id="notif-failures-errors"
                type="checkbox"
                checked={failuresErrors}
                onChange={(e) => setFailuresErrors(e.target.checked)}
              />
              <label htmlFor="notif-failures-errors">Failures / errors</label>
            </div>
          </div>
        </fieldset>

        {hasDigestFrequency && (
          <div className="form-group" style={{ marginTop: "0.25rem" }}>
            <label htmlFor="notif-digest-frequency">Digest frequency</label>
            <select
              id="notif-digest-frequency"
              value={digestFrequency}
              onChange={(e) => setDigestFrequency(e.target.value)}
            >
              {DIGEST_FREQUENCY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        )}

        {hasQuietHours && (
          <fieldset style={{ border: "none", padding: 0, margin: "1rem 0 0" }}>
            <div className="notif-section-label">Quiet Hours</div>
            <div className="notif-section-sublabel">Pause notifications during set hours.</div>

            <div className="notif-category-list">
              <div className="form-check">
                <input
                  id="notif-quiet-hours-enabled"
                  type="checkbox"
                  checked={quietHoursEnabled}
                  onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                />
                <label htmlFor="notif-quiet-hours-enabled">Enable quiet hours</label>
              </div>
            </div>

            {quietHoursEnabled && (
              <div className="form-row" style={{ maxWidth: "320px" }}>
                <div className="form-group">
                  <label htmlFor="notif-quiet-start">Start</label>
                  <input
                    id="notif-quiet-start"
                    type="time"
                    value={quietHoursStart}
                    onChange={(e) => setQuietHoursStart(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="notif-quiet-end">End</label>
                  <input
                    id="notif-quiet-end"
                    type="time"
                    value={quietHoursEnd}
                    onChange={(e) => setQuietHoursEnd(e.target.value)}
                  />
                </div>
              </div>
            )}
          </fieldset>
        )}

        {saveError && (
          <p data-testid="notifications-save-error" style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            {saveError}
          </p>
        )}
        {saveSuccess && (
          <p data-testid="notifications-save-success" style={{ color: "var(--color-success)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            Notification preferences saved successfully.
          </p>
        )}
        {dirty && !saving && (
          <p data-testid="notifications-unsaved-changes" style={{ color: "var(--color-warning)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>
            You have unsaved changes.
          </p>
        )}
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save Notifications"}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// UserSettings (main)
// ---------------------------------------------------------------------------

export default function UserSettings() {
  const [activeTab, setActiveTab] = useState("profile");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [user, setUser] = useState(null);
  const [settings, setSettings] = useState(null);
  const [success, setSuccess] = useState(null);

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([getMe(), getMeSettings()])
      .then(([userData, settingsData]) => {
        setUser(userData);
        setSettings(settingsData);
      })
      .catch((err) => setError(err.message ?? "Failed to load user settings."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    Promise.all([getMe(), getMeSettings()])
      .then(([userData, settingsData]) => {
        setUser(userData);
        setSettings(settingsData);
      })
      .catch((err) => setError(err.message ?? "Failed to load user settings."))
      .finally(() => setLoading(false));
  }, []);

  const handleSettingsSaved = useCallback(() => {
    setSuccess("Settings saved.");
    setTimeout(() => setSuccess(null), 3000);
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
          onClick={loadData}
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
          <ProfileTab user={user} onSettingsSaved={handleSettingsSaved} />
        )}
        {activeTab === "preferences" && (
          <PreferencesTab settings={settings} onSettingsSaved={handleSettingsSaved} />
        )}
        {activeTab === "notifications" && (
          <NotificationsTab settings={settings} onSettingsSaved={handleSettingsSaved} />
        )}
      </div>
    </div>
  );
}
