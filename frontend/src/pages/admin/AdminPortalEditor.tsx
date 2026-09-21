import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type {
  AdoProjectsResponse,
  AdoWorkItemType,
  AdoWorkItemTypesResponse,
  Category,
  FieldDefinition,
  FieldType,
  Portal,
} from "../../types";

const FIELD_TYPES: FieldType[] = [
  "text",
  "textarea",
  "number",
  "select",
  "multiselect",
  "date",
  "checkbox",
  "email",
];

function emptyField(): FieldDefinition {
  return {
    name: "",
    label: "",
    type: "text",
    required: false,
    placeholder: "",
    help_text: "",
    options: [],
    default: null,
    ado_field_ref: null,
  };
}

export default function AdminPortalEditor() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();

  const [categories, setCategories] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState<string>("");
  const [adoProject, setAdoProject] = useState("");
  const [workItemType, setWorkItemType] = useState("Issue");
  const [isActive, setIsActive] = useState(true);
  const [fields, setFields] = useState<FieldDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(editing);

  // Azure DevOps metadata for the project / work-item-type pickers.
  const [ado, setAdo] = useState<AdoProjectsResponse | null>(null);
  const [workItemTypes, setWorkItemTypes] = useState<AdoWorkItemType[]>([]);

  useEffect(() => {
    api.get<Category[]>("/api/categories").then(setCategories).catch(() => {});
    api.get<AdoProjectsResponse>("/api/ado/projects").then(setAdo).catch(() => {});
  }, []);

  // (Re)load the work-item types whenever the selected project changes.
  // An empty project means "use the server default".
  useEffect(() => {
    if (ado && !ado.configured) return;
    const qs = adoProject ? `?project=${encodeURIComponent(adoProject)}` : "";
    api
      .get<AdoWorkItemTypesResponse>(`/api/ado/work-item-types${qs}`)
      .then((r) => setWorkItemTypes(r.work_item_types))
      .catch(() => setWorkItemTypes([]));
  }, [adoProject, ado]);

  useEffect(() => {
    if (!editing) return;
    api.get<Portal[]>("/api/portals").then((all) => {
      const p = all.find((x) => x.id === id);
      if (p) {
        setName(p.name);
        setDescription(p.description);
        setCategoryId(p.category_id || "");
        setAdoProject(p.ado_project || "");
        setWorkItemType(p.work_item_type);
        setIsActive(p.is_active);
        setFields(p.fields);
      }
      setLoading(false);
    });
  }, [editing, id]);

  const updateField = (idx: number, patch: Partial<FieldDefinition>) =>
    setFields((prev) => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    // Basic client-side validation of field names.
    for (const f of fields) {
      if (!/^[a-zA-Z0-9_]+$/.test(f.name)) {
        setError(`Field key "${f.name || "(blank)"}" must be alphanumeric/underscore only.`);
        return;
      }
      if (!f.label) {
        setError(`Field "${f.name}" needs a label.`);
        return;
      }
    }

    const payload = {
      name,
      description,
      category_id: categoryId || null,
      ado_project: adoProject || null,
      work_item_type: workItemType,
      is_active: isActive,
      fields,
    };
    setBusy(true);
    try {
      if (editing) await api.patch(`/api/portals/${id}`, payload);
      else await api.post("/api/portals", payload);
      navigate("/admin");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="container muted">Loading…</div>;

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>{editing ? "Edit Portal" : "New Portal"}</h1>
      <p className="subtitle">
        Title and Discussion are always shown to users. Add any extra fields below.
      </p>

      {error && <div className="alert error">{error}</div>}

      <form onSubmit={save}>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Details</h2>
          <div className="field">
            <label>Name *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="row" style={{ gap: 16 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Category</label>
              <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                <option value="">General (uncategorized)</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Active</label>
              <select value={isActive ? "yes" : "no"} onChange={(e) => setIsActive(e.target.value === "yes")}>
                <option value="yes">Active (visible to users)</option>
                <option value="no">Inactive (hidden)</option>
              </select>
            </div>
          </div>
          <div className="row" style={{ gap: 16 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>ADO Project</label>
              {ado?.configured ? (
                <select value={adoProject} onChange={(e) => setAdoProject(e.target.value)}>
                  <option value="">
                    Server default{ado.default_project ? ` (${ado.default_project})` : ""}
                  </option>
                  {/* Preserve a previously-saved value even if it's not in the list */}
                  {adoProject &&
                    !ado.projects.some((p) => p.name === adoProject) && (
                      <option value={adoProject}>{adoProject} (not found)</option>
                    )}
                  {ado.projects.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={adoProject}
                  onChange={(e) => setAdoProject(e.target.value)}
                  placeholder="Leave blank to use the default project"
                />
              )}
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Work Item Type</label>
              {ado?.configured && workItemTypes.length > 0 ? (
                <select value={workItemType} onChange={(e) => setWorkItemType(e.target.value)}>
                  {workItemType &&
                    !workItemTypes.some((t) => t.name === workItemType) && (
                      <option value={workItemType}>{workItemType} (not found)</option>
                    )}
                  {workItemTypes.map((t) => (
                    <option key={t.reference_name || t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={workItemType}
                  onChange={(e) => setWorkItemType(e.target.value)}
                  placeholder="Issue, Bug, Task…"
                />
              )}
            </div>
          </div>
          {ado && !ado.configured && (
            <p className="help">
              Connect Azure DevOps (set ADO_ORG_URL / ADO_PAT) to pick the project and
              work-item type from a list.
            </p>
          )}
          {ado?.error && (
            <p className="help" style={{ color: "var(--danger)" }}>
              Couldn&apos;t load Azure DevOps metadata: {ado.error}
            </p>
          )}
        </div>

        <div className="card" style={{ marginTop: 20 }}>
          <div className="row between">
            <h2 style={{ margin: 0 }}>Custom Fields</h2>
            <button
              type="button"
              className="btn secondary small"
              onClick={() => setFields((f) => [...f, emptyField()])}
            >
              + Add field
            </button>
          </div>

          {fields.length === 0 && (
            <p className="muted" style={{ marginTop: 12 }}>
              No custom fields. Only Title and Discussion will be shown.
            </p>
          )}

          {fields.map((f, idx) => (
            <div key={idx} className="card" style={{ marginTop: 14, background: "var(--hover)" }}>
              <div className="row between">
                <strong>Field {idx + 1}</strong>
                <button
                  type="button"
                  className="btn danger small"
                  onClick={() => setFields((prev) => prev.filter((_, i) => i !== idx))}
                >
                  Remove
                </button>
              </div>
              <div className="row" style={{ gap: 12, marginTop: 10 }}>
                <div className="field" style={{ flex: 1, marginBottom: 10 }}>
                  <label>Key * (a-z, 0-9, _)</label>
                  <input value={f.name} onChange={(e) => updateField(idx, { name: e.target.value })} />
                </div>
                <div className="field" style={{ flex: 1, marginBottom: 10 }}>
                  <label>Label *</label>
                  <input value={f.label} onChange={(e) => updateField(idx, { label: e.target.value })} />
                </div>
                <div className="field" style={{ width: 150, marginBottom: 10 }}>
                  <label>Type</label>
                  <select
                    value={f.type}
                    onChange={(e) => updateField(idx, { type: e.target.value as FieldType })}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>

              {(f.type === "select" || f.type === "multiselect") && (
                <div className="field" style={{ marginBottom: 10 }}>
                  <label>Options (comma-separated)</label>
                  <input
                    value={f.options.join(", ")}
                    onChange={(e) =>
                      updateField(idx, {
                        options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                      })
                    }
                  />
                </div>
              )}

              <div className="row" style={{ gap: 12 }}>
                <div className="field" style={{ flex: 1, marginBottom: 10 }}>
                  <label>Help text</label>
                  <input value={f.help_text} onChange={(e) => updateField(idx, { help_text: e.target.value })} />
                </div>
                <div className="field" style={{ flex: 1, marginBottom: 10 }}>
                  <label>ADO field ref (optional)</label>
                  <input
                    value={f.ado_field_ref || ""}
                    onChange={(e) => updateField(idx, { ado_field_ref: e.target.value || null })}
                    placeholder="e.g. Microsoft.VSTS.Common.Priority"
                  />
                </div>
              </div>
              <label style={{ fontWeight: 400, display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={f.required}
                  onChange={(e) => updateField(idx, { required: e.target.checked })}
                  style={{ width: "auto" }}
                />
                Required
              </label>
            </div>
          ))}
        </div>

        <div className="row" style={{ marginTop: 20 }}>
          <button className="btn" disabled={busy}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create portal"}
          </button>
          <button type="button" className="btn secondary" onClick={() => navigate("/admin")}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
