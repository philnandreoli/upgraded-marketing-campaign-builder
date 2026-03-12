import { useCallback, useEffect, useRef, useState } from "react";
import {
  addCampaignMember,
  listCampaignMembers,
  listUsers,
  removeCampaignMember,
  updateCampaignMemberRole,
} from "../api";

const CAMPAIGN_ROLES = ["editor", "viewer"];
const SPINNER_SIZE = 14;
const DROPDOWN_CLOSE_DELAY = 150;

// ---------------------------------------------------------------------------
// Custom role dropdown — fully styled, replaces native <select>
// ---------------------------------------------------------------------------
function RoleDropdown({ value, onChange, className, disabled }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div className={`role-dropdown ${className || ""}`} ref={wrapRef}>
      <button
        type="button"
        className="role-dropdown-trigger"
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
      >
        <span>{value}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {open && (
        <ul className="role-dropdown-menu">
          {CAMPAIGN_ROLES.map((r) => (
            <li
              key={r}
              className={`role-dropdown-item${r === value ? " selected" : ""}`}
              onMouseDown={() => { onChange(r); setOpen(false); }}
            >
              {r}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role selector — inline dropdown that PATCHes the member role on change
// ---------------------------------------------------------------------------
function MemberRoleSelect({ campaignId, userId, currentRole, onUpdated }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = async (e) => {
    const newRole = e.target.value;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateCampaignMemberRole(campaignId, userId, newRole);
      onUpdated(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
      <RoleDropdown
        value={currentRole}
        onChange={(newRole) => handleChange({ target: { value: newRole } })}
        disabled={saving}
        className="member-role-select-wrap"
      />
      {saving && <span className="spinner" style={{ width: SPINNER_SIZE, height: SPINNER_SIZE }} />}
      {error && (
        <span style={{ fontSize: "0.75rem", color: "var(--color-danger)" }} title={error}>
          ⚠
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Add-member form — user search autocomplete + role selector
// ---------------------------------------------------------------------------
function AddMemberForm({ campaignId, existingUserIds, onAdded }) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [role, setRole] = useState("viewer");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const debounceRef = useRef(null);
  const [showDropdown, setShowDropdown] = useState(false);

  const doSearch = useCallback(async (term) => {
    if (!term.trim()) {
      setResults([]);
      setShowDropdown(false);
      return;
    }
    setSearchLoading(true);
    setSearchError(null);
    try {
      const users = await listUsers(term);
      setResults(users.filter((u) => u.is_active && !existingUserIds.includes(u.id)));
      setShowDropdown(true);
    } catch (err) {
      setSearchError(err.message);
      setResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [existingUserIds]);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    setSelectedUser(null);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 300);
  };

  const handleSelectUser = (user) => {
    setSelectedUser(user);
    setSearch(user.display_name || user.email || user.id);
    setShowDropdown(false);
    setResults([]);
  };

  const handleAdd = async () => {
    if (!selectedUser) return;
    setAdding(true);
    setAddError(null);
    try {
      const member = await addCampaignMember(campaignId, selectedUser.id, role);
      onAdded(member, selectedUser);
      setSearch("");
      setSelectedUser(null);
      setRole("viewer");
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="add-member">
      <h3>Add Member</h3>
      <div className="add-member-row">
        {/* User search */}
        <div className="add-member-search-wrap">
          <input
            type="search"
            className="add-member-search"
            placeholder="Search by name or email…"
            value={search}
            onChange={handleSearchChange}
            onFocus={() => results.length > 0 && setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), DROPDOWN_CLOSE_DELAY)}
          />
          {searchLoading && (
            <span
              className="spinner add-member-search-spinner"
              style={{ width: SPINNER_SIZE, height: SPINNER_SIZE }}
            />
          )}
          {showDropdown && results.length > 0 && (
            <ul className="add-member-dropdown">
              {results.map((u) => (
                <li
                  key={u.id}
                  onMouseDown={() => handleSelectUser(u)}
                >
                  <span className="add-member-dropdown-name">{u.display_name || "—"}</span>
                  {u.email && (
                    <span className="add-member-dropdown-email">{u.email}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {showDropdown && !searchLoading && results.length === 0 && search.trim() && (
            <div className="add-member-no-results">
              No users found.
            </div>
          )}
        </div>

        {/* Role selector */}
        <RoleDropdown
          value={role}
          onChange={setRole}
          className="add-member-role-wrap"
        />

        {/* Add button */}
        <button
          className="btn btn-primary"
          onClick={handleAdd}
          disabled={!selectedUser || adding}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.875rem" }}
        >
          {adding ? <><span className="spinner" style={{ width: SPINNER_SIZE, height: SPINNER_SIZE }} /> Adding…</> : "Add"}
        </button>
      </div>

      {searchError && (
        <p className="add-member-error">
          Search failed: {searchError}
        </p>
      )}
      {addError && (
        <p className="add-member-error">
          {addError}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compact add-member form for sidebar — inline search + role + add
// ---------------------------------------------------------------------------
function CompactAddMemberForm({ campaignId, existingUserIds, onAdded }) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [role, setRole] = useState("viewer");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const debounceRef = useRef(null);

  const doSearch = useCallback(async (term) => {
    if (!term.trim()) { setResults([]); setShowDropdown(false); return; }
    setSearchLoading(true);
    try {
      const users = await listUsers(term);
      setResults(users.filter((u) => u.is_active && !existingUserIds.includes(u.id)));
      setShowDropdown(true);
    } catch { setResults([]); }
    finally { setSearchLoading(false); }
  }, [existingUserIds]);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    setSelectedUser(null);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 300);
  };

  const handleSelectUser = (user) => {
    setSelectedUser(user);
    setSearch(user.display_name || user.email || user.id);
    setShowDropdown(false);
    setResults([]);
  };

  const handleAdd = async () => {
    if (!selectedUser) return;
    setAdding(true);
    setAddError(null);
    try {
      const member = await addCampaignMember(campaignId, selectedUser.id, role);
      onAdded(member, selectedUser);
      setSearch("");
      setSelectedUser(null);
      setRole("viewer");
    } catch (err) { setAddError(err.message); }
    finally { setAdding(false); }
  };

  return (
    <div className="compact-add-form">
      <div className="compact-add-search-wrap">
        <input
          type="search"
          className="compact-add-search"
          placeholder="Name or email…"
          value={search}
          onChange={handleSearchChange}
          onFocus={() => results.length > 0 && setShowDropdown(true)}
          onBlur={() => setTimeout(() => setShowDropdown(false), DROPDOWN_CLOSE_DELAY)}
        />
        {searchLoading && (
          <span className="spinner compact-add-spinner" style={{ width: 12, height: 12 }} />
        )}
        {showDropdown && results.length > 0 && (
          <ul className="add-member-dropdown">
            {results.map((u) => (
              <li key={u.id} onMouseDown={() => handleSelectUser(u)}>
                <span className="add-member-dropdown-name">{u.display_name || "—"}</span>
                {u.email && <span className="add-member-dropdown-email">{u.email}</span>}
              </li>
            ))}
          </ul>
        )}
        {showDropdown && !searchLoading && results.length === 0 && search.trim() && (
          <div className="add-member-no-results">No users found.</div>
        )}
      </div>
      <div className="compact-add-actions">
        <RoleDropdown
          value={role}
          onChange={setRole}
          className="compact-add-role-wrap"
        />
        <button
          className="btn btn-primary compact-add-btn"
          onClick={handleAdd}
          disabled={!selectedUser || adding}
        >
          {adding ? "…" : "Add"}
        </button>
      </div>
      {addError && <p className="add-member-error">{addError}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TeamMembersCompact — sidebar variant (names only + expandable add form)
// ---------------------------------------------------------------------------
export function TeamMembersCompact({ campaignId, canManage }) {
  const [members, setMembers] = useState([]);
  const [userMap, setUserMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await listCampaignMembers(campaignId);
      setMembers(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [campaignId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!canManage) return;
    listUsers("").then((users) => {
      const map = {};
      users.forEach((u) => { map[u.id] = { display_name: u.display_name, email: u.email }; });
      setUserMap(map);
    }).catch(() => {});
  }, [canManage]);

  const getUserLabel = (userId) => {
    const info = userMap[userId];
    if (!info) return userId;
    return info.display_name || info.email || userId;
  };

  const handleMemberAdded = (member, user) => {
    setMembers((prev) => {
      const exists = prev.find((m) => m.user_id === member.user_id);
      if (exists) return prev.map((m) => (m.user_id === member.user_id ? { ...m, role: member.role } : m));
      return [...prev, member];
    });
    if (user) {
      setUserMap((prev) => ({ ...prev, [user.id]: { display_name: user.display_name, email: user.email } }));
    }
    setShowAddForm(false);
  };

  const existingUserIds = members.map((m) => m.user_id);

  return (
    <div className="card sidebar-team">
      <div className="sidebar-team-header">
        <h3>Team</h3>
        {canManage && (
          <button
            className={`sidebar-team-add-btn${showAddForm ? " active" : ""}`}
            onClick={() => setShowAddForm((v) => !v)}
            title="Add member"
          >
            {showAddForm ? "✕" : "+"}
          </button>
        )}
      </div>

      {loading ? (
        <div className="loading" style={{ padding: "0.5rem" }}>
          <span className="spinner" style={{ width: 14, height: 14 }} />
        </div>
      ) : (
        <ul className="sidebar-team-list">
          {members.map((m) => (
            <li key={m.user_id} className="sidebar-team-member">
              <span className="sidebar-team-name">{getUserLabel(m.user_id)}</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", flexWrap: "wrap" }}>
                <span
                  className="badge"
                  style={{
                    background: m.role === "owner" ? "rgba(99,102,241,0.15)" : "rgba(148,163,184,0.12)",
                    color: m.role === "owner" ? "var(--color-primary-hover)" : "var(--color-text-dim)",
                    fontSize: "0.65rem",
                    padding: "0.12rem 0.45rem",
                  }}
                >
                  {m.role}
                </span>
                {m.via_workspace && (
                  <span
                    className="badge"
                    title={`Access via workspace: ${m.workspace_name ?? "workspace"}`}
                    style={{
                      background: "rgba(16,185,129,0.12)",
                      color: "var(--color-success, #10b981)",
                      fontSize: "0.6rem",
                      padding: "0.1rem 0.35rem",
                    }}
                  >
                    via {m.workspace_name ?? "workspace"}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {showAddForm && canManage && (
        <CompactAddMemberForm
          campaignId={campaignId}
          existingUserIds={existingUserIds}
          onAdded={handleMemberAdded}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TeamMembersSection — main exported component
// ---------------------------------------------------------------------------
export default function TeamMembersSection({ campaignId, canManage }) {
  const [members, setMembers] = useState([]);
  const [userMap, setUserMap] = useState({}); // userId -> { display_name, email }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [removeError, setRemoveError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await listCampaignMembers(campaignId);
      setMembers(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    load();
  }, [load]);

  // When canManage, try to fetch user display info via the admin API
  useEffect(() => {
    if (!canManage) return;
    listUsers("")
      .then((users) => {
        const map = {};
        users.forEach((u) => { map[u.id] = { display_name: u.display_name, email: u.email }; });
        setUserMap(map);
      })
      .catch(() => {
        // Non-admin owners can't call the admin API — fall back gracefully
      });
  }, [canManage]);

  const handleRoleUpdated = (updated) => {
    setMembers((prev) =>
      prev.map((m) => (m.user_id === updated.user_id ? { ...m, role: updated.role } : m))
    );
  };

  const handleRemove = async (userId) => {
    if (!confirm("Remove this member from the campaign?")) return;
    setRemoveError(null);
    try {
      await removeCampaignMember(campaignId, userId);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
    } catch (err) {
      setRemoveError(err.message);
    }
  };

  const handleMemberAdded = (member, user) => {
    setMembers((prev) => {
      const exists = prev.find((m) => m.user_id === member.user_id);
      if (exists) return prev.map((m) => (m.user_id === member.user_id ? { ...m, role: member.role } : m));
      return [...prev, member];
    });
    if (user) {
      setUserMap((prev) => ({ ...prev, [user.id]: { display_name: user.display_name, email: user.email } }));
    }
  };

  const getUserLabel = (userId) => {
    const info = userMap[userId];
    if (!info) return userId;
    return info.display_name || info.email || userId;
  };

  const getUserEmail = (userId) => userMap[userId]?.email ?? null;

  const existingUserIds = members.map((m) => m.user_id);

  return (
    <div className="card">
      <h2>👥 Team Members</h2>

      {loading ? (
        <div className="loading"><span className="spinner" /> Loading members…</div>
      ) : error ? (
        <p style={{ color: "var(--color-danger)", fontSize: "0.875rem" }}>Error: {error}</p>
      ) : members.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem" }}>No members found.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                {["Name", "Email", "Campaign Role", ...(canManage ? ["Actions"] : [])].map((h) => (
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
              {members.map((m) => (
                <tr key={m.user_id} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "0.6rem 0.75rem", fontWeight: 500 }}>
                    {getUserLabel(m.user_id)}
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem", color: "var(--color-text-muted)" }}>
                    {getUserEmail(m.user_id) ?? "—"}
                  </td>
                  <td style={{ padding: "0.6rem 0.75rem" }}>
                    {canManage && m.role !== "owner" && !m.via_workspace ? (
                      <MemberRoleSelect
                        campaignId={campaignId}
                        userId={m.user_id}
                        currentRole={m.role}
                        onUpdated={handleRoleUpdated}
                      />
                    ) : (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                        <span
                          className="badge"
                          style={{
                            background: m.role === "owner" ? "rgba(99,102,241,0.15)" : "rgba(148,163,184,0.15)",
                            color: m.role === "owner" ? "var(--color-primary-hover)" : "var(--color-text-muted)",
                            fontSize: "0.75rem",
                          }}
                        >
                          {m.role}
                        </span>
                        {m.via_workspace && (
                          <span
                            className="badge"
                            title={`Access via workspace: ${m.workspace_name ?? "workspace"}`}
                            style={{
                              background: "rgba(16,185,129,0.12)",
                              color: "var(--color-success, #10b981)",
                              fontSize: "0.68rem",
                              padding: "0.1rem 0.4rem",
                            }}
                          >
                            via {m.workspace_name ?? "workspace"}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  {canManage && (
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      {m.role !== "owner" && (
                        <button
                          className="btn btn-outline"
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.75rem",
                            borderColor: "var(--color-danger)",
                            color: "var(--color-danger)",
                          }}
                          onClick={() => handleRemove(m.user_id)}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {removeError && (
        <p style={{ color: "var(--color-danger)", fontSize: "0.8rem", marginTop: "0.5rem" }}>
          {removeError}
        </p>
      )}

      {canManage && (
        <AddMemberForm
          campaignId={campaignId}
          existingUserIds={existingUserIds}
          onAdded={handleMemberAdded}
        />
      )}
    </div>
  );
}
