import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import FieldRenderer from "../components/FieldRenderer";
import type { Portal, Ticket } from "../types";

export default function PortalForm() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [portal, setPortal] = useState<Portal | null>(null);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!slug) return;
    api
      .get<Portal>(`/api/portals/${slug}`)
      .then((p) => {
        setPortal(p);
        const defaults: Record<string, unknown> = {};
        p.fields.forEach((f) => {
          if (f.default != null) defaults[f.name] = f.default;
        });
        setValues(defaults);
      })
      .catch(() => setError("Portal not found."))
      .finally(() => setLoading(false));
  }, [slug]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!portal) return;
    setError(null);
    setBusy(true);
    try {
      const ticket = await api.post<Ticket>("/api/tickets", {
        portal_id: portal.id,
        title,
        description,
        field_values: values,
      });
      navigate(`/tickets/${ticket.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="container muted">Loading…</div>;
  if (!portal) return <div className="container"><div className="alert error">{error}</div></div>;

  return (
    <div className="container narrow">
      <div className="breadcrumb">
        <Link to="/">Browse</Link> / {portal.category_name} / {portal.name}
      </div>
      <h1>{portal.name}</h1>
      <p className="subtitle">{portal.description}</p>

      {error && <div className="alert error">{error}</div>}

      <form onSubmit={submit} className="card">
        {/* Title & Description are always present */}
        <div className="field">
          <label htmlFor="title">
            Title <span className="req">*</span>
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Short summary of your request"
          />
        </div>
        <div className="field">
          <label htmlFor="description">Discussion</label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe your request in detail"
          />
        </div>

        {portal.fields.map((f) => (
          <FieldRenderer
            key={f.name}
            field={f}
            value={values[f.name]}
            onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))}
          />
        ))}

        <button className="btn" disabled={busy}>
          {busy ? "Submitting…" : "Submit request"}
        </button>
      </form>
    </div>
  );
}
