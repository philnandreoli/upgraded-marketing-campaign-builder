import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { listUsers, updateUserRoles, deactivateUser, listAllCampaigns, listWorkspaces, moveCampaign } from "../api";
import WorkspaceBadge from "../components/WorkspaceBadge.jsx";

const ROLES = ["admin", "campaign_builder", "viewer"];
const INCOMPATIBLE = { campaign_builder: "viewer", viewer: "campaign_builder" };

function RoleCheckboxes({ userId, currentRoles, onRolesChange }) {
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
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
      {ROLES.map((r) => (
        <label
          key={r}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.25rem",
            fontSize: "0.8rem",
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.6 : 1,
          }}
        >
          <input
            type="checkbox"
            checked={currentRoles.includes(r)}
            disabled={saving}
            onChange={() => handleToggle(r)}
          />
          {r.replace(/_/g, " ")}
        </label>
      ))}
      {saving && <span className="spinner" style={{ width: 14, height: 14 }} />}
      {error && (
        <span style={{ fontSize: "0.75rem", color: "var(--color-danger)" }} title={error}>
          ⚠ {error}
        </span>
      )}
    </span>
  );
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
  const [moveError, setMoveError] = useState(null);
  const [activeTab, setActiveTab] = useState("users");
  const navigate = useNavigate();

  const fetchUsers = useCallback(async (term = "") => {
    setLoadingUsers(true);
    setUsersError(null);
    try {
      setUsers(await listUsers(term));
    } catch (err) {
      setUsersError(err.message);
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const fetchCampaigns = useCallback(async () => {
    setLoadingCampaigns(true);
    setCampaignsError(null);
    try {
      setCampaigns(await listAllCampaigns());
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

  useEffect(() => {
    fetchUsers("");
    fetchCampaigns();
    fetchWorkspaces();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    fetchUsers(val);
  };

  const handleRolesChange = async (userId, newRoles) => {
    const updated = await updateUserRoles(userId, newRoles);
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, roles: updated.roles } : u)));
  };

  const handleDeactivate = async (userId) => {
    if (!confirm("Deactivate this user? They will lose access to the platform.")) return;
    setDeactivateError(null);
    try {
      await deactivateUser(userId);
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: false } : u)));
    } catch (err) {
      setDeactivateError(err.message);
    }
  };

  const handleMoveCampaign = async (campaignId, workspaceId) => {
    if (!workspaceId) return;
    setMoveError(null);
    try {
      await moveCampaign(campaignId, workspaceId);
      await fetchCampaigns();
    } catch (err) {
      setMoveError(err.message);
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
                      {["Display Name", "Email", "Roles", "Active", "Date Added", "Actions"].map((h) => (
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
                    {users.map((u) => (
                      <tr
                        key={u.id}
                        style={{
                          borderBottom: "1px solid var(--color-border)",
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
                          {u.is_active ? (
                            <RoleCheckboxes
                              userId={u.id}
                              currentRoles={u.roles}
                              onRolesChange={handleRolesChange}
                            />
                          ) : (
                            <span style={{ color: "var(--color-text-dim)", fontSize: "0.8rem" }}>
                              {u.roles.map((r) => r.replace(/_/g, " ")).join(", ")}
                            </span>
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
                          {u.is_active && (
                            <button
                              className="btn btn-outline"
                              style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
                              onClick={() => handleDeactivate(u.id)}
                            >
                              Deactivate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── All Campaigns Tab ─────────────────────────────────────────── */}
      {activeTab === "campaigns" && (
        <>
          <div className="section-header">
            <h2>All Campaigns</h2>
          </div>

          {moveError && (
            <div className="card" style={{ marginBottom: "0.75rem", padding: "0.6rem 1rem" }}>
              <p style={{ color: "var(--color-danger)", fontSize: "0.875rem", margin: 0 }}>
                ⚠ Move failed: {moveError}
              </p>
            </div>
          )}

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
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                              <WorkspaceBadge orphaned={true} />
                              <select
                                style={{
                                  padding: "0.2rem 0.4rem",
                                  fontSize: "0.75rem",
                                  background: "var(--color-surface-2)",
                                  border: "1px solid var(--color-border)",
                                  borderRadius: "var(--radius)",
                                  color: "var(--color-text)",
                                }}
                                defaultValue=""
                                onChange={(e) => handleMoveCampaign(c.id, e.target.value)}
                              >
                                <option value="" disabled>Assign…</option>
                                {workspaces.map((ws) => (
                                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                                ))}
                              </select>
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "0.6rem 1rem" }}>
                          <span className={`badge badge-${c.status}`}>
                            {(c.status ?? "unknown").replace(/_/g, " ")}
                          </span>
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
    </div>
  );
}
