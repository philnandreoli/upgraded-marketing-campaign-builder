import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { listUsers, updateUserRoles, deactivateUser, reactivateUser, listAllCampaigns, listWorkspaces, searchEntraUsers, provisionUser, getUserWorkspaces, getAdminTemplateAnalytics } from "../api";
import WorkspaceBadge from "../components/WorkspaceBadge.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useConfirm } from "../ConfirmDialogContext";

const ROLES = ["admin", "campaign_builder", "viewer"];
const INCOMPATIBLE = { campaign_builder: "viewer", viewer: "campaign_builder" };

const ROLE_LABELS = {
  admin: "Admin",
  campaign_builder: "Campaign Builder",
  viewer: "Viewer",
};

function RoleCheckboxes({ userId, currentRoles, onRolesChange, disabled = false }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleToggle = async (toggledRole) => {
    setSaving(true);
    setError(null);
    try {
      let next;
      if (currentRoles.includes(toggledRole)) {
        // Remove the role (but don't allow empty)
        next = currentRoles.filter((r) => r !== toggledRole);
        if (next.length === 0) {
          setError("At least one role is required.");
          setSaving(false);
          return;
        }
      } else {
        // Add the role & remove incompatible
        const incomp = INCOMPATIBLE[toggledRole];
        next = [...currentRoles.filter((r) => r !== incomp), toggledRole];
      }
      await onRolesChange(userId, next);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
      {ROLES.map((r) => {
        const isActive = currentRoles.includes(r);
        const pillClass = [
          "role-pill",
          isActive ? "role-pill--active" : "",
          saving ? "role-pill--saving" : "",
          disabled ? "role-pill--disabled" : "",
        ]
          .filter(Boolean)
          .join(" ");

        return (
          <button
            key={r}
            className={pillClass}
            data-role={r}
            disabled={disabled || saving}
            onClick={() => handleToggle(r)}
            aria-pressed={isActive}
            aria-label={
              disabled
                ? ROLE_LABELS[r]
                : isActive
                ? `Remove ${ROLE_LABELS[r]}`
                : `Add ${ROLE_LABELS[r]}`
            }
            title={
              disabled
                ? ROLE_LABELS[r]
                : isActive
                ? `Remove ${ROLE_LABELS[r]}`
                : `Add ${ROLE_LABELS[r]}`
            }
          >
            {isActive && <span className="role-pill__check">✓</span>}
            {ROLE_LABELS[r]}
          </button>
        );
      })}
      {saving && <span className="spinner" style={{ width: 14, height: 14, flexShrink: 0 }} />}
      {error && (
        <span style={{ fontSize: "0.75rem", color: "var(--color-danger)" }} title={error}>
          ⚠ {error}
        </span>
      )}
    </span>
  );
}

/** Return the best human-readable label for an Entra ID directory user. */
function getEntraUserLabel(user) {
  return user.display_name ?? user.mail ?? user.user_principal_name ?? user.id;
}

export default function Admin() {
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(true);
  const [search, setSearch] = useState("");
  const [usersError, setUsersError] = useState(null);
  const [campaignsError, setCampaignsError] = useState(null);
  const [workspacesError, setWorkspacesError] = useState(null);
  const [deactivateError, setDeactivateError] = useState(null);
  const [reactivateError, setReactivateError] = useState(null);
  const [activeTab, setActiveTab] = useState("users");

  // Template analytics state
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState(null);

  // Workspace access drill-down state (inline in user table)
  const [expandedUserId, setExpandedUserId] = useState(null);
  const [userWorkspaces, setUserWorkspaces] = useState({});
  const [loadingUserWs, setLoadingUserWs] = useState({});
  const navigate = useNavigate();
  const confirm = useConfirm();

  // Users pagination state
  const PAGE_SIZE = 25;
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Campaigns pagination state
  const CAMPAIGNS_PAGE_SIZE = 50;
  const [campaignsPage, setCampaignsPage] = useState(1);
  const [campaignsTotalCount, setCampaignsTotalCount] = useState(0);

  // Entra ID directory search state
  const [entraSearch, setEntraSearch] = useState("");
  const [entraResults, setEntraResults] = useState([]);
  const [entraLoading, setEntraLoading] = useState(false);
  const [entraError, setEntraError] = useState(null);
  const [selectedEntraUser, setSelectedEntraUser] = useState(null);
  const [provisionRoles, setProvisionRoles] = useState(["viewer"]);
  const [provisionError, setProvisionError] = useState(null);
  const [provisionSuccess, setProvisionSuccess] = useState(null);
  const [provisioning, setProvisioning] = useState(false);
  const entraSearchTimer = useRef(null);

  const fetchUsers = useCallback(async (term = "", pg = 1) => {
    setLoadingUsers(true);
    setUsersError(null);
    try {
      const { users: data, totalCount: total } = await listUsers(term, { page: pg, pageSize: PAGE_SIZE });
      setUsers(data);
      setTotalCount(total);
    } catch (err) {
      setUsersError(err.message);
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const fetchCampaigns = useCallback(async (pg = 1) => {
    setLoadingCampaigns(true);
    setCampaignsError(null);
    try {
      const offset = (pg - 1) * CAMPAIGNS_PAGE_SIZE;
      const { campaigns: data, totalCount: total } = await listAllCampaigns({ limit: CAMPAIGNS_PAGE_SIZE, offset });
      setCampaigns(data);
      setCampaignsTotalCount(total);
    } catch (err) {
      setCampaignsError(err.message);
    } finally {
      setLoadingCampaigns(false);
    }
  }, []);

  const fetchWorkspaces = useCallback(async () => {
    setLoadingWorkspaces(true);
    setWorkspacesError(null);
    try {
      setWorkspaces(await listWorkspaces());
    } catch (err) {
      setWorkspacesError(err.message);
    } finally {
      setLoadingWorkspaces(false);
    }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      setAnalytics(await getAdminTemplateAnalytics());
    } catch (err) {
      setAnalyticsError(err.message);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const handleExpandUser = useCallback(async (userId) => {
    if (expandedUserId === userId) {
      setExpandedUserId(null);
      return;
    }
    setExpandedUserId(userId);
    if (userWorkspaces[userId]) return;
    setLoadingUserWs((prev) => ({ ...prev, [userId]: true }));
    try {
      const data = await getUserWorkspaces(userId);
      setUserWorkspaces((prev) => ({ ...prev, [userId]: data }));
    } catch (err) {
      setUserWorkspaces((prev) => ({ ...prev, [userId]: { error: err.message } }));
    } finally {
      setLoadingUserWs((prev) => ({ ...prev, [userId]: false }));
    }
  }, [expandedUserId, userWorkspaces]);

  useEffect(() => {
    fetchUsers("", 1);
    fetchCampaigns();
    fetchWorkspaces();
    fetchAnalytics();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    setPage(1);
    fetchUsers(val, 1);
  };

  const handleRolesChange = async (userId, newRoles) => {
    const updated = await updateUserRoles(userId, newRoles);
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, roles: updated.roles } : u)));
  };

  const handleDeactivate = async (userId) => {
    const confirmed = await confirm({
      title: "Deactivate user?",
      message: "Deactivate this user? They will lose access to the platform.",
      confirmLabel: "Deactivate",
      destructive: true,
    });
    if (!confirmed) return;
    setDeactivateError(null);
    try {
      await deactivateUser(userId);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: false } : u)));
    } catch (err) {
      setDeactivateError(err.message);
    }
  };

  const handleReactivate = async (userId) => {
    const confirmed = await confirm({
      title: "Reactivate user?",
      message: "Reactivate this user? They will regain access to the platform.",
      confirmLabel: "Reactivate",
      destructive: false,
    });
    if (!confirmed) return;
    setReactivateError(null);
    try {
      await reactivateUser(userId);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: true } : u)));
    } catch (err) {
      setReactivateError(err.message);
    }
  };

  const handleEntraSearchChange = (e) => {
    const val = e.target.value;
    setEntraSearch(val);
    setSelectedEntraUser(null);
    setEntraError(null);
    setProvisionSuccess(null);

    if (entraSearchTimer.current) clearTimeout(entraSearchTimer.current);
    if (!val.trim()) {
      setEntraResults([]);
      return;
    }
    entraSearchTimer.current = setTimeout(async () => {
      setEntraLoading(true);
      try {
        setEntraResults(await searchEntraUsers(val.trim()));
      } catch (err) {
        setEntraError(err.message);
        setEntraResults([]);
      } finally {
        setEntraLoading(false);
      }
    }, 400);
  };

  const handleSelectEntraUser = (user) => {
    setSelectedEntraUser(user);
    setEntraResults([]);
    setEntraSearch(getEntraUserLabel(user));
    setProvisionError(null);
    setProvisionSuccess(null);
  };

  const handleProvisionUser = async () => {
    if (!selectedEntraUser) return;
    setProvisioning(true);
    setProvisionError(null);
    setProvisionSuccess(null);
    try {
      await provisionUser(
        selectedEntraUser.id,
        selectedEntraUser.mail ?? selectedEntraUser.user_principal_name,
        selectedEntraUser.display_name,
        provisionRoles,
      );
      setProvisionSuccess(
        `${getEntraUserLabel(selectedEntraUser)} has been added as ${provisionRoles.map((r) => ROLE_LABELS[r]).join(", ")}.`,
      );
      setSelectedEntraUser(null);
      setEntraSearch("");
      setEntraResults([]);
      setProvisionRoles(["viewer"]);
      await fetchUsers("", 1);
      setSearch("");
      setPage(1);
    } catch (err) {
      setProvisionError(err.message);
    } finally {
      setProvisioning(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  return (
    <div>
      {/* ── Tab Navigation ──────────────────────────────────────────────── */}
      <div className="pipeline-tabs" style={{ marginBottom: "1.5rem" }}>
        {[
          { key: "users", label: "User Management" },
          { key: "campaigns", label: "All Campaigns" },
          { key: "workspaces", label: "Workspaces" },
          { key: "templates", label: "Template Analytics" },
        ].map((tab) => (
          <button
            key={tab.key}
            className={`pipeline-tab completed${activeTab === tab.key ? " selected" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Users Tab ─────────────────────────────────────────────────── */}
      {activeTab === "users" && (
        <>
          <div className="section-header">
            <h2>User Management</h2>
          </div>

          {/* ── Add User from Directory ──────────────────────────────── */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <h3 style={{ marginTop: 0, marginBottom: "0.75rem", fontSize: "1rem", fontWeight: 600 }}>
              Add User from Directory
            </h3>
            <p style={{ fontSize: "0.875rem", color: "var(--color-text-muted)", marginBottom: "0.75rem" }}>
              Search your Microsoft Entra ID directory to pre-provision a user with a specific role
              before they log in for the first time.
            </p>

            <div className="ws-add-member-form" style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", borderBottom: "none", marginBottom: 0, paddingBottom: 0 }}>
              {/* Directory search input + autocomplete */}
              <div style={{ position: "relative", flex: "1 1 260px", maxWidth: 400 }}>
                <input
                  type="search"
                  placeholder="Search by name or email…"
                  value={entraSearch}
                  onChange={handleEntraSearchChange}
                  style={{ width: "100%", boxSizing: "border-box" }}
                  aria-label="Search Entra ID directory"
                  aria-expanded={entraResults.length > 0}
                  aria-haspopup="listbox"
                />
                {entraLoading && (
                  <span
                    className="spinner"
                    style={{ position: "absolute", right: "0.6rem", top: "50%", transform: "translateY(-50%)", width: 14, height: 14 }}
                  />
                )}
                {entraResults.length > 0 && (
                  <ul
                    role="listbox"
                    style={{
                      position: "absolute",
                      top: "calc(100% + 4px)",
                      left: 0,
                      right: 0,
                      zIndex: 50,
                      margin: 0,
                      padding: "0.25rem 0",
                      listStyle: "none",
                      background: "var(--color-surface)",
                      border: "1px solid var(--color-border)",
                      borderRadius: "var(--radius)",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                      maxHeight: 240,
                      overflowY: "auto",
                    }}
                  >
                    {entraResults.map((u) => (
                      <li
                        key={u.id}
                        role="option"
                        aria-selected={selectedEntraUser?.id === u.id}
                        onClick={() => handleSelectEntraUser(u)}
                        style={{
                          padding: "0.5rem 0.75rem",
                          cursor: "pointer",
                          fontSize: "0.875rem",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-surface-2)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                      >
                        <span style={{ fontWeight: 500 }}>{getEntraUserLabel(u)}</span>
                        {(u.mail ?? u.user_principal_name) && (
                          <span style={{ marginLeft: "0.4rem", color: "var(--color-text-muted)", fontSize: "0.8rem" }}>
                            {u.mail ?? u.user_principal_name}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Role selector (multi-select pills) */}
              <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                {ROLES.map((r) => {
                  const isActive = provisionRoles.includes(r);
                  const pillClass = [
                    "role-pill",
                    isActive ? "role-pill--active" : "",
                    provisioning ? "role-pill--saving" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");

                  return (
                    <button
                      key={r}
                      type="button"
                      className={pillClass}
                      data-role={r}
                      disabled={provisioning}
                      onClick={() => {
                        setProvisionRoles((prev) => {
                          if (prev.includes(r)) {
                            const next = prev.filter((x) => x !== r);
                            return next.length === 0 ? prev : next;
                          }
                          const incomp = INCOMPATIBLE[r];
                          return [...prev.filter((x) => x !== incomp), r];
                        });
                      }}
                      aria-pressed={isActive}
                      aria-label={isActive ? `Remove ${ROLE_LABELS[r]}` : `Add ${ROLE_LABELS[r]}`}
                      title={isActive ? `Remove ${ROLE_LABELS[r]}` : `Add ${ROLE_LABELS[r]}`}
                    >
                      {isActive && <span className="role-pill__check">✓</span>}
                      {ROLE_LABELS[r]}
                    </button>
                  );
                })}
              </span>

              {/* Add button */}
              <button
                className="btn btn-primary"
                style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
                disabled={!selectedEntraUser || provisioning || provisionRoles.length === 0}
                onClick={handleProvisionUser}
              >
                {provisioning ? <><span className="spinner" style={{ width: 13, height: 13, marginRight: "0.4rem" }} />Adding…</> : "Add"}
              </button>
            </div>

            {entraError && (
              <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--color-danger)" }}>
                ⚠ {entraError}
              </p>
            )}
            {provisionError && (
              <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--color-danger)" }}>
                ⚠ {provisionError}
              </p>
            )}
            {provisionSuccess && (
              <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--color-success)" }}>
                ✓ {provisionSuccess}
              </p>
            )}
          </div>

          <div className="card">
            {/* Search bar */}
            <div className="form-group" style={{ marginBottom: "1rem" }}>
              <input
                type="search"
                placeholder="Search by name or email…"
                value={search}
                onChange={handleSearchChange}
                style={{ maxWidth: 360 }}
              />
            </div>

            {deactivateError && (
              <p style={{ color: "var(--color-danger)", marginBottom: "0.75rem", fontSize: "0.875rem" }}>
                Deactivate failed: {deactivateError}
              </p>
            )}

            {reactivateError && (
              <p style={{ color: "var(--color-danger)", marginBottom: "0.75rem", fontSize: "0.875rem" }}>
                Reactivate failed: {reactivateError}
              </p>
            )}

            {loadingUsers ? (
              <div className="loading">
                <span className="spinner" /> Loading users…
              </div>
            ) : usersError ? (
              <p style={{ color: "var(--color-danger)" }}>Error: {usersError}</p>
            ) : users.length === 0 ? (
              <p style={{ color: "var(--color-text-muted)" }}>No users found.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Display Name", "Email", "Roles", "Workspaces", "Active", "Date Added", "Actions"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "0.5rem 0.75rem",
                            color: "var(--color-text-muted)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => {
                      const isExpanded = expandedUserId === u.id;
                      const wsData = userWorkspaces[u.id];
                      const wsLoading = loadingUserWs[u.id];
                      return (
                      <Fragment key={u.id}>
                      <tr
                        className={isExpanded ? "ws-access-row ws-access-row--expanded" : "ws-access-row"}
                        style={{
                          borderBottom: isExpanded ? "none" : "1px solid var(--color-border)",
                          opacity: u.is_active ? 1 : 0.5,
                        }}
                      >
                        <td style={{ padding: "0.6rem 0.75rem", fontWeight: 500 }}>
                          {u.display_name ?? <span style={{ color: "var(--color-text-dim)" }}>—</span>}
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem", color: "var(--color-text-muted)" }}>
                          {u.email ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem" }}>
                          <RoleCheckboxes
                            userId={u.id}
                            currentRoles={u.roles}
                            onRolesChange={handleRolesChange}
                            disabled={!u.is_active}
                          />
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem", color: "var(--color-text-muted)" }}>
                          {u.workspace_count > 0 ? (
                            <span
                              className="ws-access-count-link"
                              role="button"
                              tabIndex={0}
                              onClick={() => handleExpandUser(u.id)}
                              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleExpandUser(u.id); } }}
                              aria-expanded={isExpanded}
                            >
                              <span className="ws-access-chevron">{isExpanded ? "▾" : "▸"}</span>
                              {u.workspace_count}
                            </span>
                          ) : (
                            <span style={{ color: "var(--color-text-dim)" }}>0</span>
                          )}
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem" }}>
                          <span
                            style={{
                              display: "inline-block",
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: u.is_active ? "var(--color-success)" : "var(--color-text-dim)",
                              marginRight: "0.4rem",
                            }}
                          />
                          {u.is_active ? "Active" : "Inactive"}
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem", color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                          {formatDate(u.created_at)}
                        </td>
                        <td style={{ padding: "0.6rem 0.75rem" }}>
                          {u.is_active ? (
                            <button
                              className="btn btn-outline"
                              style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
                              onClick={() => handleDeactivate(u.id)}
                            >
                              Deactivate
                            </button>
                          ) : (
                            <button
                              className="btn btn-outline"
                              style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", borderColor: "var(--color-success)", color: "var(--color-success)" }}
                              onClick={() => handleReactivate(u.id)}
                            >
                              Reactivate
                            </button>
                          )}
                        </td>
                      </tr>

                      {/* Expanded workspace detail row */}
                      {isExpanded && (
                        <tr className="ws-access-detail-row">
                          <td colSpan={7} style={{ padding: 0, borderBottom: "1px solid var(--color-border)" }}>
                            <div className="ws-access-detail">
                              {wsLoading ? (
                                <div className="loading" style={{ padding: "0.75rem 1.5rem" }}>
                                  <span className="spinner" style={{ width: 14, height: 14 }} /> Loading workspaces…
                                </div>
                              ) : wsData?.error ? (
                                <p style={{ color: "var(--color-danger)", padding: "0.75rem 1.5rem", fontSize: "0.8rem" }}>
                                  ⚠ {wsData.error}
                                </p>
                              ) : wsData && Array.isArray(wsData) && wsData.length > 0 ? (
                                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                                  <thead>
                                    <tr>
                                      {["Workspace", "Type", "Workspace Role", "Added"].map((h) => (
                                        <th
                                          key={h}
                                          style={{
                                            textAlign: "left",
                                            padding: "0.4rem 0.75rem",
                                            color: "var(--color-text-muted)",
                                            fontWeight: 600,
                                            fontSize: "0.78rem",
                                          }}
                                        >
                                          {h}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {wsData.map((ws) => (
                                      <tr
                                        key={ws.workspace_id}
                                        className="ws-access-workspace-row"
                                        onClick={() => navigate(`/workspaces/${ws.workspace_id}`)}
                                        style={{ cursor: "pointer" }}
                                      >
                                        <td style={{ padding: "0.4rem 0.75rem", fontWeight: 500 }}>
                                          {ws.workspace_name}
                                        </td>
                                        <td style={{ padding: "0.4rem 0.75rem" }}>
                                          {ws.is_personal ? (
                                            <span className="badge" style={{ background: "rgba(99,102,241,0.15)", color: "var(--color-primary-hover)", fontSize: "0.68rem" }}>
                                              🏠 Personal
                                            </span>
                                          ) : (
                                            <span className="badge" style={{ background: "rgba(148,163,184,0.12)", color: "var(--color-text-dim)", fontSize: "0.68rem" }}>
                                              📁 Team
                                            </span>
                                          )}
                                        </td>
                                        <td style={{ padding: "0.4rem 0.75rem" }}>
                                          <span className={`ws-role-badge ws-role-badge--${ws.role}`}>
                                            {ws.role}
                                          </span>
                                        </td>
                                        <td style={{ padding: "0.4rem 0.75rem", color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                                          {formatDate(ws.added_at)}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                <p style={{ color: "var(--color-text-muted)", padding: "0.75rem 1.5rem", fontSize: "0.82rem" }}>
                                  No workspace memberships found.
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                      </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination controls */}
            {!loadingUsers && !usersError && totalCount > 0 && (() => {
              const totalPages = Math.ceil(totalCount / PAGE_SIZE);
              return (
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: "1rem",
                  fontSize: "0.875rem",
                  color: "var(--color-text-muted)",
                }}>
                  <span>
                    Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, totalCount)} of {totalCount} users
                  </span>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <button
                      className="btn btn-outline"
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.8rem" }}
                      disabled={page <= 1}
                      onClick={() => { const p = page - 1; setPage(p); fetchUsers(search, p); }}
                    >
                      Previous
                    </button>
                    <span>Page {page} of {totalPages}</span>
                    <button
                      className="btn btn-outline"
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.8rem" }}
                      disabled={page >= totalPages}
                      onClick={() => { const p = page + 1; setPage(p); fetchUsers(search, p); }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </>
      )}

      {/* ── All Campaigns Tab ─────────────────────────────────────────── */}
      {activeTab === "campaigns" && (
        <>
          <div className="section-header">
            <h2>All Campaigns</h2>
          </div>

          {loadingCampaigns ? (
            <div className="loading">
              <span className="spinner" /> Loading campaigns…
            </div>
          ) : campaignsError ? (
            <div className="card">
              <p style={{ color: "var(--color-danger)" }}>Error: {campaignsError}</p>
            </div>
          ) : campaigns.length === 0 ? (
            <div className="card">
              <p style={{ color: "var(--color-text-muted)" }}>No campaigns found.</p>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Campaign", "Goal", "Owner", "Workspace", "Status", "Created"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "0.75rem 1rem",
                            color: "var(--color-text-muted)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                            background: "var(--color-surface)",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c) => (
                      <tr
                        key={c.id}
                        style={{ borderBottom: "1px solid var(--color-border)" }}
                      >
                        <td style={{ padding: "0.6rem 1rem", fontWeight: 500 }}>
                          {c.product_or_service ?? c.id}
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.goal ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>
                          {c.owner_id ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 1rem" }}>
                          {c.workspace_id ? (
                            <WorkspaceBadge workspace={c.workspace} linkTo={true} />
                          ) : (
                            <WorkspaceBadge orphaned={true} />
                          )}
                        </td>
                        <td style={{ padding: "0.6rem 1rem" }}>
                          <StatusBadge status={c.status ?? "unknown"} />
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                          {formatDate(c.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

            {/* Campaigns pagination controls */}
            {!loadingCampaigns && !campaignsError && campaignsTotalCount > 0 && (() => {
              const totalPages = Math.ceil(campaignsTotalCount / CAMPAIGNS_PAGE_SIZE);
              return (
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: "1rem",
                  fontSize: "0.875rem",
                  color: "var(--color-text-muted)",
                }}>
                  <span>
                    Showing {(campaignsPage - 1) * CAMPAIGNS_PAGE_SIZE + 1}–{Math.min(campaignsPage * CAMPAIGNS_PAGE_SIZE, campaignsTotalCount)} of {campaignsTotalCount} campaigns
                  </span>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <button
                      className="btn btn-outline"
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.8rem" }}
                      disabled={campaignsPage <= 1}
                      onClick={() => { const p = campaignsPage - 1; setCampaignsPage(p); fetchCampaigns(p); }}
                    >
                      Previous
                    </button>
                    <span>Page {campaignsPage} of {totalPages}</span>
                    <button
                      className="btn btn-outline"
                      style={{ padding: "0.25rem 0.75rem", fontSize: "0.8rem" }}
                      disabled={campaignsPage >= totalPages}
                      onClick={() => { const p = campaignsPage + 1; setCampaignsPage(p); fetchCampaigns(p); }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              );
            })()}
        </>
      )}

      {/* ── Workspaces Tab ────────────────────────────────────────────── */}
      {activeTab === "workspaces" && (
        <>
          <div className="section-header">
            <h2>Workspaces</h2>
          </div>

          {loadingWorkspaces ? (
            <div className="loading">
              <span className="spinner" /> Loading workspaces…
            </div>
          ) : workspacesError ? (
            <div className="card">
              <p style={{ color: "var(--color-danger)" }}>Error: {workspacesError}</p>
            </div>
          ) : workspaces.length === 0 ? (
            <div className="card">
              <p style={{ color: "var(--color-text-muted)" }}>No workspaces found.</p>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Name", "Owner", "Members", "Campaigns", "Type", "Created"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            padding: "0.75rem 1rem",
                            color: "var(--color-text-muted)",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                            background: "var(--color-surface)",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {workspaces.map((ws) => (
                      <tr
                        key={ws.id}
                        style={{ borderBottom: "1px solid var(--color-border)", cursor: "pointer" }}
                        onClick={() => navigate(`/workspaces/${ws.id}`)}
                      >
                        <td style={{ padding: "0.6rem 1rem", fontWeight: 500 }}>
                          <WorkspaceBadge workspace={ws} linkTo={false} />
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>
                          {ws.owner_display_name ?? ws.owner_id ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>
                          {ws.member_count ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>
                          {ws.campaign_count ?? "—"}
                        </td>
                        <td style={{ padding: "0.6rem 1rem" }}>
                          {ws.is_personal ? (
                            <span className="badge" style={{ background: "rgba(99,102,241,0.15)", color: "var(--color-primary-hover)", fontSize: "0.7rem" }}>
                              🏠 Personal
                            </span>
                          ) : (
                            <span className="badge" style={{ background: "rgba(148,163,184,0.12)", color: "var(--color-text-dim)", fontSize: "0.7rem" }}>
                              📁 Team
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                          {formatDate(ws.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Template Analytics Tab ────────────────────────────────────── */}
      {activeTab === "templates" && (
        <>
          <div className="section-header">
            <h2>Template Analytics</h2>
          </div>

          {analyticsLoading ? (
            <div className="loading">
              <span className="spinner" /> Loading template analytics…
            </div>
          ) : analyticsError ? (
            <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
              <p style={{ color: "var(--color-danger)", marginBottom: "1rem" }}>Error: {analyticsError}</p>
              <button type="button" className="btn btn-outline" onClick={fetchAnalytics}>
                Retry
              </button>
            </div>
          ) : analytics && analytics.total_clones === 0 && analytics.total_templates === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
              <p style={{ color: "var(--color-text-muted)" }}>
                No template analytics yet. Mark approved campaigns as templates to start tracking.
              </p>
            </div>
          ) : analytics ? (
            <>
              {/* Summary Stats Row */}
              <div className="analytics-stats-row">
                <div className="analytics-stat-card">
                  <div className="analytics-stat-card__number">{analytics.total_templates ?? 0}</div>
                  <div className="analytics-stat-card__label">Total Templates</div>
                </div>
                <div className="analytics-stat-card">
                  <div className="analytics-stat-card__number">{analytics.total_clones ?? 0}</div>
                  <div className="analytics-stat-card__label">Total Clones</div>
                </div>
                <div className="analytics-stat-card">
                  <div className="analytics-stat-card__number">{analytics.most_popular_category ?? "—"}</div>
                  <div className="analytics-stat-card__label">Most Popular Category</div>
                </div>
                <div className="analytics-stat-card">
                  <div className="analytics-stat-card__number">
                    {analytics.avg_brand_score != null ? analytics.avg_brand_score.toFixed(1) : "—"}
                  </div>
                  <div className="analytics-stat-card__label">Avg Brand Score</div>
                </div>
              </div>

              {/* Top Templates Table */}
              {analytics.top_templates && analytics.top_templates.length > 0 && (
                <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: "1.5rem" }}>
                  <h3 style={{ padding: "1rem 1rem 0.5rem", margin: 0, fontSize: "1rem" }}>Top Templates</h3>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                          {["Rank", "Template Name", "Category", "Clone Count", "Success Rate (%)", "Avg Brand Score"].map((h) => (
                            <th
                              key={h}
                              style={{
                                textAlign: "left",
                                padding: "0.75rem 1rem",
                                color: "var(--color-text-muted)",
                                fontWeight: 600,
                                whiteSpace: "nowrap",
                                background: "var(--color-surface)",
                              }}
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.top_templates.map((t, i) => (
                          <tr key={t.template_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                            <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>{i + 1}</td>
                            <td style={{ padding: "0.6rem 1rem", fontWeight: 500 }}>
                              <a href="/templates" style={{ color: "var(--color-primary)" }}>{t.template_name}</a>
                            </td>
                            <td style={{ padding: "0.6rem 1rem", color: "var(--color-text-muted)" }}>{t.category ?? "—"}</td>
                            <td style={{ padding: "0.6rem 1rem" }}>{t.clone_count ?? 0}</td>
                            <td style={{ padding: "0.6rem 1rem" }}>
                              {t.success_rate != null ? `${(t.success_rate * 100).toFixed(1)}%` : "—"}
                            </td>
                            <td style={{ padding: "0.6rem 1rem" }}>
                              {t.avg_brand_score != null ? t.avg_brand_score.toFixed(1) : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Clone Trends Chart — vertical bar chart */}
              {analytics.monthly_trends && analytics.monthly_trends.length > 0 && (() => {
                const maxClone = Math.max(...analytics.monthly_trends.map((m) => m.clone_count), 1);
                return (
                  <div className="card" style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ margin: "0 0 1rem", fontSize: "1rem" }}>Clone Trends (Last 12 Months)</h3>
                    <div className="bar-chart" role="img" aria-label="Monthly clone trends bar chart">
                      <div className="bar-chart__bars">
                        {analytics.monthly_trends.map((m) => (
                          <div key={m.month} className="bar-chart__col">
                            <div className="bar-chart__value">{m.clone_count}</div>
                            <div
                              className="bar-chart__bar"
                              style={{ height: `${(m.clone_count / maxClone) * 100}%` }}
                              title={`${m.month}: ${m.clone_count} clones`}
                            />
                            <div className="bar-chart__label">{m.month.slice(5)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Workspace Adoption — horizontal bar chart */}
              {analytics.workspace_adoption && analytics.workspace_adoption.length > 0 && (() => {
                const maxWsClone = Math.max(...analytics.workspace_adoption.map((w) => w.clone_count), 1);
                return (
                  <div className="card" style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ margin: "0 0 1rem", fontSize: "1rem" }}>Workspace Adoption (Top 10)</h3>
                    <div className="hbar-chart">
                      {analytics.workspace_adoption.map((w) => (
                        <div key={w.workspace_id} className="hbar-chart__row">
                          <div className="hbar-chart__label">{w.workspace_name ?? w.workspace_id}</div>
                          <div className="hbar-chart__track">
                            <div
                              className="hbar-chart__bar"
                              style={{ width: `${(w.clone_count / maxWsClone) * 100}%` }}
                            />
                          </div>
                          <div className="hbar-chart__value">{w.clone_count}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
