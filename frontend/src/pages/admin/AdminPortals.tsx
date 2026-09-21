import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { Portal } from "../../types";

export default function AdminPortals() {
  const [portals, setPortals] = useState<Portal[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    api
      .get<Portal[]>("/api/portals")
      .then(setPortals)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const remove = async (p: Portal) => {
    if (!confirm(`Delete portal "${p.name}"? This cannot be undone.`)) return;
    await api.del(`/api/portals/${p.id}`);
    load();
  };

  return (
    <div className="container">
      <div className="row between">
        <div>
          <h1>Portals</h1>
          <p className="subtitle">Modular forms that front Azure DevOps work items.</p>
        </div>
        <div className="row">
          <Link className="btn secondary" to="/admin/tickets">Queue</Link>
          <Link className="btn secondary" to="/admin/categories">Categories</Link>
          <Link className="btn secondary" to="/admin/users">Users</Link>
          <Link className="btn" to="/admin/portals/new">+ New Portal</Link>
        </div>
      </div>

      {loading ? (
        <div className="muted">Loading…</div>
      ) : portals.length === 0 ? (
        <div className="empty">No portals yet. Create your first one.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Work Item Type</th>
                <th>Fields</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {portals.map((p) => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.name}</strong>
                    <div className="muted mono">{p.slug}</div>
                  </td>
                  <td>{p.category_name}</td>
                  <td>{p.work_item_type}</td>
                  <td>{p.fields.length}</td>
                  <td>
                    <span className={`badge ${p.is_active ? "synced" : "failed"}`}>
                      {p.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn secondary small" onClick={() => navigate(`/admin/portals/${p.id}`)}>
                        Edit
                      </button>
                      <button className="btn danger small" onClick={() => remove(p)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
