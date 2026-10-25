import { Fragment, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { canManageUser, grantableRoles, ROLE_LABELS } from "../../auth/roles";
import { useAuth } from "../../context/AuthContext";
import type { Portal, User, UserRole } from "../../types";

const ROLE_BADGE: Record<UserRole, string> = {
  super_admin: "failed",
  admin: "syncing",
  portal_admin: "synced",
  end_user: "pending",
};

function PortalPicker({
  portals,
  selected,
  onChange,
}: {
  portals: Portal[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  if (portals.length === 0) return <div className="muted">No portals exist yet.</div>;
  const toggle = (id: string, on: boolean) =>
    onChange(on ? [...selected, id] : selected.filter((s) => s !== id));
  return (
    <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
      {portals.map((p) => (
        <label key={p.id} style={{ fontWeight: 400, display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={selected.includes(p.id)}
            onChange={(e) => toggle(p.id, e.target.checked)}
            style={{ width: "auto" }}
          />
          {p.name}
        </label>
      ))}
    </div>
  );
}

export default function AdminUsers() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [portals, setPortals] = useState<Portal[]>([]);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("end_user");
  const [portalIds, setPortalIds] = useState<string[]>([]);
  // The user whose portal assignments are being edited, and the draft.
  const [editing, setEditing] = useState<{ id: string; portalIds: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const roles = grantableRoles(me);
  const portalName = (id: string) => portals.find((p) => p.id === id)?.name ?? "Unknown portal";

  const load = () => api.get<User[]>("/api/users").then(setUsers);
  useEffect(() => {
    void load();
    api.get<Portal[]>("/api/portals").then(setPortals).catch(() => {});
  }, []);

  const fail = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.message : fallback);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/users", {
        email,
        display_name: displayName,
        password,
        role,
        portal_ids: role === "portal_admin" ? portalIds : [],
      });
      setEmail(""); setDisplayName(""); setPassword(""); setRole("end_user"); setPortalIds([]);
      await load();
    } catch (err) {
      fail(err, "Create failed");
    }
  };

  const update = async (u: User, changes: Partial<Pick<User, "role" | "portal_ids">>) => {
    setError(null);
    try {
      await api.patch(`/api/users/${u.id}`, changes);
      await load();
      return true;
    } catch (err) {
      fail(err, "Update failed");
      return false;
    }
  };

  const changeRole = async (u: User, next: UserRole) => {
    if (await update(u, { role: next })) {
      // New portal admins usually need portals right away.
      setEditing(next === "portal_admin" ? { id: u.id, portalIds: [] } : null);
    }
  };

  const saveAssignments = async (u: User) => {
    if (editing && (await update(u, { portal_ids: editing.portalIds }))) setEditing(null);
  };

  const remove = async (u: User) => {
    if (!confirm(`Delete user ${u.email}?`)) return;
    setError(null);
    try {
      await api.del(`/api/users/${u.id}`);
      await load();
    } catch (err) {
      fail(err, "Delete failed");
    }
  };

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Users</h1>
      <p className="subtitle">
        Manage local accounts and roles. Federated users are created on first login. Super admins
        can do everything; admins manage portals, categories and users; portal admins edit only
        the portals assigned to them.
      </p>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 20 }}>
        <h2 style={{ marginTop: 0 }}>Create local user</h2>
        <form onSubmit={create}>
          <div className="row" style={{ gap: 12 }}>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Email *</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Name</label>
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Password *</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
            <div className="field" style={{ width: 160, marginBottom: 0 }}>
              <label>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
                {roles.map((r) => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
            </div>
            <button className="btn" style={{ alignSelf: "flex-end" }}>Create</button>
          </div>
          {role === "portal_admin" && (
            <div className="field" style={{ marginTop: 12, marginBottom: 0 }}>
              <label>Portals this user can edit</label>
              <PortalPicker portals={portals} selected={portalIds} onChange={setPortalIds} />
            </div>
          )}
        </form>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr><th>Email</th><th>Name</th><th>Provider</th><th>Role</th><th>Portals</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const manageable = canManageUser(me, u);
              const isEditing = editing?.id === u.id;
              return (
                <Fragment key={u.id}>
                  <tr>
                    <td>{u.email}</td>
                    <td>{u.display_name}</td>
                    <td><span className="tag">{u.provider}</span></td>
                    <td>
                      {manageable ? (
                        <select
                          value={u.role}
                          onChange={(e) => void changeRole(u, e.target.value as UserRole)}
                          style={{ width: "auto" }}
                        >
                          {roles.map((r) => (
                            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                          ))}
                        </select>
                      ) : (
                        <span className={`badge ${ROLE_BADGE[u.role]}`}>{ROLE_LABELS[u.role]}</span>
                      )}
                    </td>
                    <td>
                      {u.role === "portal_admin" ? (
                        <>
                          {u.portal_ids.length === 0 && <span className="muted">None</span>}
                          {u.portal_ids.map((id) => (
                            <span key={id} className="tag">{portalName(id)}</span>
                          ))}
                          {manageable && !isEditing && (
                            <button
                              className="btn secondary small"
                              style={{ marginLeft: 6 }}
                              onClick={() => setEditing({ id: u.id, portalIds: u.portal_ids })}
                            >
                              Edit
                            </button>
                          )}
                        </>
                      ) : (
                        <span className="muted">{u.role === "end_user" ? "—" : "All"}</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${u.is_active ? "synced" : "failed"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td>
                      {manageable && u.id !== me?.id && (
                        <button className="btn danger small" onClick={() => remove(u)}>Delete</button>
                      )}
                    </td>
                  </tr>
                  {isEditing && editing && (
                    <tr>
                      <td colSpan={7}>
                        <div className="field" style={{ marginBottom: 8 }}>
                          <label>Portals {u.email} can edit</label>
                          <PortalPicker
                            portals={portals}
                            selected={editing.portalIds}
                            onChange={(ids) => setEditing({ id: u.id, portalIds: ids })}
                          />
                        </div>
                        <div className="row">
                          <button className="btn small" onClick={() => void saveAssignments(u)}>Save</button>
                          <button className="btn secondary small" onClick={() => setEditing(null)}>Cancel</button>
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
    </div>
  );
}
