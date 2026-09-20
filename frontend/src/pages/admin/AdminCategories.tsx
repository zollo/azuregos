import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { Category } from "../../types";

export default function AdminCategories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => api.get<Category[]>("/api/categories").then(setCategories);
  useEffect(() => { void load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/categories", { name, description });
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  };

  const remove = async (c: Category) => {
    if (!confirm(`Delete "${c.name}"? Its portals move to General.`)) return;
    await api.del(`/api/categories/${c.id}`);
    await load();
  };

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Categories</h1>
      <p className="subtitle">Group portals for the end-user catalog. Uncategorized portals appear under General.</p>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 20 }}>
        <h2 style={{ marginTop: 0 }}>Add a category</h2>
        <form onSubmit={create}>
          <div className="row" style={{ gap: 12 }}>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Name *</label>
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="field" style={{ flex: 2, marginBottom: 0 }}>
              <label>Description</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <button className="btn" style={{ alignSelf: "flex-end" }}>Add</button>
          </div>
        </form>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr><th>Name</th><th>Description</th><th>Portals</th><th></th></tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.name}</strong><div className="muted mono">{c.slug}</div></td>
                <td className="muted">{c.description || "—"}</td>
                <td>{c.portal_count ?? 0}</td>
                <td>
                  <button className="btn danger small" onClick={() => remove(c)}>Delete</button>
                </td>
              </tr>
            ))}
            {categories.length === 0 && (
              <tr><td colSpan={4} className="empty">No categories yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
