import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { User, UserRole } from "../../types";

export default function AdminUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("end_user");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => api.get<User[]>("/api/users").then(setUsers);
  useEffect(() => { void load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/users", { email, display_name: displayName, password, role });
      setEmail(""); setDisplayName(""); setPassword(""); setRole("end_user");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  };

  const toggleRole = async (u: User) => {
    const next: UserRole = u.role === "admin" ? "end_user" : "admin";
    await api.patch(`/api/users/${u.id}`, { role: next });
    await load();
  };

  const remove = async (u: User) => {
    if (!confirm(`Delete user ${u.email}?`)) return;
    try {
      await api.del(`/api/users/${u.id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  };

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Users</h1>
      <p className="subtitle">Manage local accounts and roles. Federated users are created on first login.</p>

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
            <div className="field" style={{ width: 140, marginBottom: 0 }}>
              <label>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
                <option value="end_user">End user</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <button className="btn" style={{ alignSelf: "flex-end" }}>Create</button>
          </div>
        </form>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr><th>Email</th><th>Name</th><th>Provider</th><th>Role</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>{u.display_name}</td>
                <td><span className="tag">{u.provider}</span></td>
                <td>
                  <span className={`badge ${u.role === "admin" ? "syncing" : "pending"}`}>
                    {u.role === "admin" ? "Admin" : "End user"}
                  </span>
                </td>
                <td>
                  <span className={`badge ${u.is_active ? "synced" : "failed"}`}>
                    {u.is_active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td>
                  <div className="row">
                    <button className="btn secondary small" onClick={() => toggleRole(u)}>
                      Make {u.role === "admin" ? "end user" : "admin"}
                    </button>
                    <button className="btn danger small" onClick={() => remove(u)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
