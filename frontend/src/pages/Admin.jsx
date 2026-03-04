import { useEffect, useState, useCallback } from "react";
import { listUsers, updateUserRole, deactivateUser, listAllCampaigns } from "../api";

const ROLES = ["admin", "campaign_builder", "viewer"];

function RoleSelect({ userId, currentRole, onRoleChange }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = async (e) => {
    const newRole = e.target.value;
    setSaving(true);
    setError(null);
    try {
      await onRoleChange(userId, newRole);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
      <select
        value={currentRole}
        onChange={handleChange}
        disabled={saving}
        style={{
          padding: "0.3rem 0.5rem",
          fontSize: "0.8rem",
          background: "var(--color-surface-2)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius)",
          color: "var(--color-text)",
        }}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      {saving && <span className="spinner" style={{ width: 14, height: 14 }} />}
      {error && (
        <span style={{ fontSize: "0.75rem", color: "var(--color-danger)" }} title={error}>
          ⚠
        </span>
      )}
    </span>
  );
}

export default function Admin() {
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [search, setSearch] = useState("");
  const [usersError, setUsersError] = useState(null);
  const [campaignsError, setCampaignsError] = useState(null);
  const [deactivateError, setDeactivateError] = useState(null);

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

  const fetchCampaigns = async () => {
    setLoadingCampaigns(true);
    setCampaignsError(null);
    try {
      setCampaigns(await listAllCampaigns());
    } catch (err) {
      setCampaignsError(err.message);
    } finally {
      setLoadingCampaigns(false);
    }
  };

  useEffect(() => {
    fetchUsers("");
    fetchCampaigns();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    fetchUsers(val);
  };

  const handleRoleChange = async (userId, newRole) => {
    const updated = await updateUserRole(userId, newRole);
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: updated.role } : u)));
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

  const formatDate = (iso) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  return (
    <div>
      {/* ── Users Section ─────────────────────────────────────────────── */}
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
                  {["Display Name", "Email", "Role", "Active", "Date Added", "Actions"].map((h) => (
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
                        <RoleSelect
                          userId={u.id}
                          currentRole={u.role}
                          onRoleChange={handleRoleChange}
                        />
                      ) : (
                        <span style={{ color: "var(--color-text-dim)", fontSize: "0.8rem" }}>
                          {u.role.replace(/_/g, " ")}
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

      {/* ── All Campaigns Section ──────────────────────────────────────── */}
      <div className="section-header" style={{ marginTop: "1.5rem" }}>
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
                  {["Campaign", "Goal", "Owner", "Status", "Created"].map((h) => (
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
    </div>
  );
}
