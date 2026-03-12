import { useCallback, useEffect, useRef, useState } from "react";
import {
  addWorkspaceMember,
  listWorkspaceMembers,
  listUsers,
  removeWorkspaceMember,
  updateWorkspaceMemberRole,
} from "../api";

const WORKSPACE_ROLES = ["creator", "contributor", "viewer"];
const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };
const SPINNER_SIZE = 14;
const DROPDOWN_CLOSE_DELAY = 150;

// ---------------------------------------------------------------------------
// Role selector — inline dropdown that PATCHes the member role on change
// ---------------------------------------------------------------------------
function WorkspaceMemberRoleSelect({ workspaceId, userId, currentRole, onUpdated }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = async (e) => {
    const newRole = e.target.value;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateWorkspaceMemberRole(workspaceId, userId, newRole);
      onUpdated(updated);
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
        aria-label={`Role for member ${userId}`}
        className="member-role-select"
      >
        {WORKSPACE_ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </select>
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
function AddWorkspaceMemberForm({ workspaceId, existingUserIds, onAdded }) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [role, setRole] = useState("contributor");
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
      const member = await addWorkspaceMember(workspaceId, selectedUser.id, role);
      onAdded(member, selectedUser);
      setSearch("");
      setSelectedUser(null);
      setRole("contributor");
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
                <li key={u.id} onMouseDown={() => handleSelectUser(u)}>
                  <span className="add-member-dropdown-name">{u.display_name || "—"}</span>
                  {u.email && (
                    <span className="add-member-dropdown-email">{u.email}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {showDropdown && !searchLoading && results.length === 0 && search.trim() && (
            <div className="add-member-no-results">No users found.</div>
          )}
        </div>

        {/* Role selector */}
        <select
          className="add-member-role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Role for new workspace member"
        >
          {WORKSPACE_ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>

        {/* Add button */}
        <button
          className="btn btn-primary"
          onClick={handleAdd}
          disabled={!selectedUser || adding}
          style={{ padding: "0.55rem 1.1rem", fontSize: "0.875rem" }}
        >
          {adding ? (
            <><span className="spinner" style={{ width: SPINNER_SIZE, height: SPINNER_SIZE }} /> Adding…</>
          ) : (
            "Add"
          )}
        </button>
      </div>

      {searchError && (
        <p className="add-member-error">Search failed: {searchError}</p>
      )}
      {addError && (
        <p className="add-member-error">{addError}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WorkspaceMembersSection — main exported component
// ---------------------------------------------------------------------------
/**
 * WorkspaceMembersSection — manage members of a workspace.
 *
 * Props:
 *   workspaceId  string   — workspace identifier
 *   isPersonal   boolean  — true for personal workspaces (owner-only, read-only membership)
 *   canManage    boolean  — true when the current user is a CREATOR or admin
 */
export default function WorkspaceMembersSection({ workspaceId, isPersonal = false, canManage = false }) {
  const [members, setMembers] = useState([]);
  const [userMap, setUserMap] = useState({}); // userId -> { display_name, email }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [removeError, setRemoveError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await listWorkspaceMembers(workspaceId);
      setMembers(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

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
    if (!confirm("Remove this member from the workspace?")) return;
    setRemoveError(null);
    try {
      await removeWorkspaceMember(workspaceId, userId);
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
      setUserMap((prev) => ({
        ...prev,
        [user.id]: { display_name: user.display_name, email: user.email },
      }));
    }
  };

  const getUserLabel = (userId) => {
    const info = userMap[userId];
    if (!info) return userId;
    return info.display_name || info.email || userId;
  };

  const getUserEmail = (userId) => userMap[userId]?.email ?? null;

  const existingUserIds = members.map((m) => m.user_id);
  const creatorCount = members.filter((m) => m.role === "creator").length;

  // Whether the remove button should be shown for a given member
  const canRemoveMember = (member) => {
    if (isPersonal) return false; // personal workspace — owner is always sole creator
    if (!canManage) return false;
    if (member.role === "creator" && creatorCount <= 1) return false; // cannot remove last creator
    return true;
  };

  // Whether the role dropdown should be editable for a given member
  const canEditRole = (member) => {
    if (isPersonal) return false;
    if (!canManage) return false;
    // Cannot downgrade the last creator via the inline select
    if (member.role === "creator" && creatorCount <= 1) return false;
    return true;
  };

  return (
    <div className="card workspace-members">
      <h2>👥 Workspace Members</h2>

      {loading ? (
        <div className="loading"><span className="spinner" /> Loading members…</div>
      ) : error ? (
        <p style={{ color: "var(--color-danger)", fontSize: "0.875rem" }}>Error: {error}</p>
      ) : members.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.875rem" }}>No members found.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="workspace-members-table">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                {["Name", "Email", "Workspace Role", ...(canManage && !isPersonal ? ["Actions"] : [])].map((h) => (
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
                    {canEditRole(m) ? (
                      <WorkspaceMemberRoleSelect
                        workspaceId={workspaceId}
                        userId={m.user_id}
                        currentRole={m.role}
                        onUpdated={handleRoleUpdated}
                      />
                    ) : (
                      <span className={`workspace-role-badge workspace-role-badge--${m.role}`}>
                        {ROLE_LABELS[m.role] ?? m.role}
                      </span>
                    )}
                  </td>
                  {canManage && !isPersonal && (
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      {canRemoveMember(m) && (
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

      {canManage && !isPersonal && (
        <AddWorkspaceMemberForm
          workspaceId={workspaceId}
          existingUserIds={existingUserIds}
          onAdded={handleMemberAdded}
        />
      )}
    </div>
  );
}
