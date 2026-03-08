import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  getWorkspace,
  updateWorkspace,
  deleteWorkspace,
  listWorkspaceMembers,
  addWorkspaceMember,
  updateWorkspaceMemberRole,
  removeWorkspaceMember,
  listUsers,
} from "../api";
import { useUser } from "../UserContext";
import { useWorkspace } from "../WorkspaceContext";

const WORKSPACE_ROLES = ["creator", "contributor", "viewer"];
const ROLE_LABELS = { creator: "Creator", contributor: "Contributor", viewer: "Viewer" };

function getInitials(name) {
  if (!name?.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function RoleDropdown({ value, onChange, disabled, ariaLabel }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="custom-select" ref={ref}>
      <button
        type="button"
        className="custom-select-trigger"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={open}
      >
        <span>{ROLE_LABELS[value] ?? value}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {open && (
        <ul className="custom-select-menu">
          {WORKSPACE_ROLES.map((r) => (
            <li
              key={r}
              className={`custom-select-option${r === value ? " selected" : ""}`}
              onClick={() => { onChange(r); setOpen(false); }}
            >
              {ROLE_LABELS[r]}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AddMemberForm({ workspaceId, onAdded }) {
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [role, setRole] = useState("contributor");
  const [selectedUser, setSelectedUser] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    const val = e.target.value;
    setSearch(val);
    setSelectedUser(null);
    if (!val.trim()) { setResults([]); return; }
    setSearching(true);
    try {
      const users = await listUsers(val);
      setResults(users);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleAdd = async () => {
    if (!selectedUser) return;
    setSaving(true);
    setError(null);
    try {
      await addWorkspaceMember(workspaceId, selectedUser.id, role);
      setSearch("");
      setResults([]);
      setSelectedUser(null);
      onAdded();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ws-add-member-form">
      <h4 style={{ marginBottom: "0.75rem" }}>Add Member</h4>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 220px" }}>
          <input
            type="search"
            placeholder="Search user by name or email…"
            value={search}
            onChange={handleSearch}
            style={{ width: "100%" }}
          />
          {results.length > 0 && !selectedUser && (
            <ul className="ws-user-search-results">
              {results.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    className="ws-user-search-result-btn"
                    onClick={() => {
                      setSelectedUser(u);
                      setSearch(u.display_name ?? u.email ?? u.id);
                      setResults([]);
                    }}
                  >
                    <span className="ws-user-search-avatar">{getInitials(u.display_name ?? u.email)}</span>
                    <span>
                      <span className="ws-user-search-name">{u.display_name ?? "—"}</span>
                      <span className="ws-user-search-email"> {u.email}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {searching && (
            <span className="spinner" style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", width: 14, height: 14 }} />
          )}
        </div>
        <RoleDropdown
          value={role}
          onChange={setRole}
          ariaLabel="Role for new member"
        />
        <button
          className="btn btn-primary"
          onClick={handleAdd}
          disabled={!selectedUser || saving}
        >
          {saving ? "Adding…" : "Add"}
        </button>
      </div>
      {error && (
        <p style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginTop: "0.5rem" }}>{error}</p>
      )}
    </div>
  );
}

function MemberTableRow({ workspaceId, member, isPersonal, onUpdated, onRemoved }) {
  const [role, setRole] = useState(member.role);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleRoleChange = async (newRole) => {
    setSaving(true);
    setError(null);
    try {
      await updateWorkspaceMemberRole(workspaceId, member.user_id ?? member.id, newRole);
      setRole(newRole);
      onUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!confirm(`Remove ${member.display_name ?? member.email} from this workspace?`)) return;
    setSaving(true);
    setError(null);
    try {
      await removeWorkspaceMember(workspaceId, member.user_id ?? member.id);
      onRemoved();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  return (
    <tr style={{ borderBottom: "1px solid var(--color-border)", opacity: saving ? 0.7 : 1 }}>
      <td style={{ padding: "0.6rem 0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="ws-member-avatar" aria-hidden="true">
            {getInitials(member.display_name ?? member.email)}
          </div>
          <span>{member.display_name ?? "—"}</span>
        </div>
      </td>
      <td style={{ padding: "0.6rem 0.75rem", color: "var(--color-text-muted)" }}>{member.email ?? "—"}</td>
      <td style={{ padding: "0.6rem 0.75rem" }}>
        {isPersonal ? (
          <span className={`workspace-role-badge workspace-role-badge--${role}`}>
            {ROLE_LABELS[role] ?? role}
          </span>
        ) : (
          <RoleDropdown
            value={role}
            onChange={handleRoleChange}
            disabled={saving}
            ariaLabel={`Role for ${member.display_name ?? member.email}`}
          />
        )}
        {error && (
          <span style={{ fontSize: "0.75rem", color: "var(--color-danger)", marginLeft: "0.5rem" }}>
            ⚠ {error}
          </span>
        )}
      </td>
      <td style={{ padding: "0.6rem 0.75rem" }}>
        {!isPersonal && (
          <button
            className="btn btn-outline"
            style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
            onClick={handleRemove}
            disabled={saving}
          >
            Remove
          </button>
        )}
      </td>
    </tr>
  );
}

export default function WorkspaceSettings() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAdmin } = useUser();
  const { refreshWorkspaces } = useWorkspace();

  const [workspace, setWorkspace] = useState(null);
  const [members, setMembers] = useState([]);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [error, setError] = useState(null);

  // Edit form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Delete state
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const fetchWorkspace = useCallback(() => {
    setLoadingWs(true);
    getWorkspace(id)
      .then((ws) => {
        setWorkspace(ws);
        setName(ws.name ?? "");
        setDescription(ws.description ?? "");
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingWs(false));
  }, [id]);

  const fetchMembers = useCallback(() => {
    setLoadingMembers(true);
    listWorkspaceMembers(id)
      .then(setMembers)
      .catch(() => setMembers([]))
      .finally(() => setLoadingMembers(false));
  }, [id]);

  useEffect(() => {
    fetchWorkspace();
    fetchMembers();
  }, [fetchWorkspace, fetchMembers]);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      const updated = await updateWorkspace(id, { name: name.trim(), description: description.trim() || undefined });
      setWorkspace(updated);
      setName(updated.name ?? "");
      setDescription(updated.description ?? "");
      refreshWorkspaces();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (
      !confirm(
        "Delete this workspace?\n\nWarning: All campaigns in this workspace will become orphaned (unassigned). They will not be deleted."
      )
    )
      return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteWorkspace(id);
      refreshWorkspaces();
      navigate("/workspaces");
    } catch (err) {
      setDeleteError(err.message);
      setDeleting(false);
    }
  };

  if (loadingWs) {
    return (
      <div className="loading">
        <span className="spinner" /> Loading workspace…
      </div>
    );
  }

  if (error || !workspace) {
    return (
      <div className="card">
        <p style={{ color: "var(--color-danger)" }}>{error ?? "Workspace not found."}</p>
        <Link to="/workspaces" className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          ← Back to Workspaces
        </Link>
      </div>
    );
  }

  const isCreatorOrAdmin = isAdmin || workspace.role === "creator";
  const isPersonal = workspace.is_personal;

  if (!isCreatorOrAdmin) {
    return (
      <div className="card">
        <p style={{ color: "var(--color-text-muted)" }}>You do not have permission to manage this workspace.</p>
        <Link to={`/workspaces/${id}`} className="btn btn-outline" style={{ marginTop: "0.75rem" }}>
          ← Back to Workspace
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <div style={{ marginBottom: "1rem", fontSize: "0.875rem", color: "var(--color-text-muted)" }}>
        <Link to="/workspaces">Workspaces</Link>
        {" / "}
        <Link to={`/workspaces/${id}`}>{workspace.name}</Link>
        {" / Settings"}
      </div>

      {/* ── Edit Workspace ─────────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Workspace Settings</h2>
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h3>Edit Workspace</h3>
        <form onSubmit={handleSave}>
          <div className="form-group">
            <label htmlFor="ws-settings-name">Name <span aria-hidden="true">*</span></label>
            <input
              id="ws-settings-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              disabled={isPersonal}
              readOnly={isPersonal}
              title={isPersonal ? "Personal workspace name cannot be changed" : undefined}
            />
          </div>
          <div className="form-group">
            <label htmlFor="ws-settings-description">Description</label>
            <textarea
              id="ws-settings-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isPersonal}
              readOnly={isPersonal}
              title={isPersonal ? "Personal workspace description cannot be changed" : undefined}
            />
          </div>
          {saveError && (
            <p style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
              {saveError}
            </p>
          )}
          {saveSuccess && (
            <p style={{ color: "var(--color-success)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
              Saved successfully.
            </p>
          )}
          {!isPersonal && (
            <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
              {saving ? "Saving…" : "Save Changes"}
            </button>
          )}
          {isPersonal && (
            <p style={{ fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
              Personal workspace name and description are read-only.
            </p>
          )}
        </form>
      </div>

      {/* ── Member Management ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Members</h2>
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        {!isPersonal && (
          <AddMemberForm workspaceId={id} onAdded={fetchMembers} />
        )}

        {loadingMembers ? (
          <div className="loading" style={{ marginTop: "1rem" }}>
            <span className="spinner" /> Loading members…
          </div>
        ) : members.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", marginTop: isPersonal ? 0 : "1rem" }}>No members found.</p>
        ) : (
          <div style={{ marginTop: isPersonal ? 0 : "1.25rem" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  {["Name", "Email", "Role", "Actions"].map((h) => (
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
                  <MemberTableRow
                    key={m.user_id ?? m.id}
                    workspaceId={id}
                    member={m}
                    isPersonal={isPersonal}
                    onUpdated={fetchMembers}
                    onRemoved={fetchMembers}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Danger Zone ────────────────────────────────────────────────── */}
      <div className="section-header">
        <h2 style={{ color: "var(--color-danger)" }}>Danger Zone</h2>
      </div>

      <div className="card ws-danger-zone" style={{ marginBottom: "2rem" }}>
        <p style={{ marginBottom: "0.75rem", fontSize: "0.875rem" }}>
          <strong>Delete Workspace</strong>
          <br />
          Warning: All campaigns in this workspace will become orphaned (unassigned). They will not be deleted.
        </p>
        {deleteError && (
          <p style={{ color: "var(--color-danger)", fontSize: "0.875rem", marginBottom: "0.75rem" }}>
            {deleteError}
          </p>
        )}
        <button
          className="btn btn-danger"
          onClick={handleDelete}
          disabled={isPersonal || deleting}
          title={isPersonal ? "Personal workspaces cannot be deleted" : undefined}
        >
          {deleting ? "Deleting…" : "Delete Workspace"}
        </button>
        {isPersonal && (
          <p style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--color-text-dim)" }}>
            Personal workspaces cannot be deleted.
          </p>
        )}
      </div>
    </div>
  );
}
