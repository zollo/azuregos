import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import Icon from "../../components/Icon";
import IconPicker from "../../components/IconPicker";
import Markdown from "../../components/Markdown";
import type { Category } from "../../types";

export default function AdminCategories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => api.get<Category[]>("/api/categories").then(setCategories);
  useEffect(() => {
    void load();
  }, []);

  const reset = () => {
    setEditingId(null);
    setName("");
    setDescription("");
    setIcon("");
  };

  const edit = (c: Category) => {
    setEditingId(c.id);
    setName(c.name);
    setDescription(c.description);
    setIcon(c.icon || "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const payload = { name, description, icon };
      if (editingId) await api.patch(`/api/categories/${editingId}`, payload);
      else await api.post("/api/categories", payload);
      reset();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  };

  const remove = async (c: Category) => {
    if (!confirm(`Delete "${c.name}"? Its portals move to General.`)) return;
    await api.del(`/api/categories/${c.id}`);
    if (editingId === c.id) reset();
    await load();
  };

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Categories</h1>
      <p className="subtitle">
        Group portals for the end-user catalog. Uncategorized portals appear under General.
      </p>

      {error && <div className="alert error">{error}</div>}

      <div className="card" style={{ marginBottom: 20 }}>
        <h2 style={{ marginTop: 0 }}>{editingId ? "Edit category" : "Add a category"}</h2>
        <form onSubmit={submit}>
          <div className="field">
            <label>Name *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label>Icon</label>
            <IconPicker value={icon} onChange={setIcon} />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
            <div className="help">Markdown supported.</div>
            {description.trim() && (
              <div className="preview" style={{ marginTop: 8 }}>
                <Markdown>{description}</Markdown>
              </div>
            )}
          </div>
          <div className="row">
            <button className="btn">{editingId ? "Save changes" : "Add"}</button>
            {editingId && (
              <button type="button" className="btn secondary" onClick={reset}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table>
          <thead>
            <tr><th></th><th>Name</th><th>Description</th><th>Portals</th><th></th></tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id}>
                <td><Icon name={c.icon || "folder"} /></td>
                <td><strong>{c.name}</strong><div className="muted mono">{c.slug}</div></td>
                <td className="muted">{c.description ? c.description.split("\n")[0] : "—"}</td>
                <td>{c.portal_count ?? 0}</td>
                <td>
                  <div className="row">
                    <button className="btn secondary small" onClick={() => edit(c)}>Edit</button>
                    <button className="btn danger small" onClick={() => remove(c)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
            {categories.length === 0 && (
              <tr><td colSpan={5} className="empty">No categories yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
