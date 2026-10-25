import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { AdoConnectionStatus, AdoConnectionTestResult } from "../../types";

// A connection saved here takes precedence over the ADO_* environment
// variables; removing it reverts to them. The PAT is write-only.
export default function AdminAdoConnection() {
  const [status, setStatus] = useState<AdoConnectionStatus | null>(null);
  const [orgUrl, setOrgUrl] = useState("");
  const [pat, setPat] = useState("");
  const [project, setProject] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [test, setTest] = useState<AdoConnectionTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const apply = (s: AdoConnectionStatus) => {
    setStatus(s);
    setOrgUrl(s.stored?.org_url ?? "");
    setProject(s.stored?.default_project ?? "");
    setPat("");
  };

  useEffect(() => {
    api
      .get<AdoConnectionStatus>("/api/ado/connection")
      .then(apply)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"));
  }, []);

  const payload = () => ({ org_url: orgUrl, pat: pat || null, default_project: project });

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setNotice(null);
    setTest(null);
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const save = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      apply(await api.put<AdoConnectionStatus>("/api/ado/connection", payload()));
      setNotice("Connection saved. It now takes precedence over the environment variables.");
    });
  };

  const testConnection = () =>
    run(async () => {
      setTest(await api.post<AdoConnectionTestResult>("/api/ado/connection/test", payload()));
    });

  const remove = () => {
    const fallback = status?.environment.pat_set && status.environment.org_url
      ? "Azuregos will fall back to the environment variables."
      : "No environment connection is set, so Azure DevOps will be disconnected.";
    if (!confirm(`Remove the saved connection? ${fallback}`)) return;
    void run(async () => {
      await api.del("/api/ado/connection");
      apply(await api.get<AdoConnectionStatus>("/api/ado/connection"));
      setNotice("Saved connection removed.");
    });
  };

  const env = status?.environment;
  const stored = status?.stored;

  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Azure DevOps connection</h1>
      <p className="subtitle">
        The organization and personal access token Azuregos uses to create and read work items.
      </p>

      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}
      {status?.error && <div className="alert error">{status.error}</div>}

      {status && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="row">
            <strong>In use:</strong>
            {status.source === "database" && (
              <span className={`badge ${status.configured ? "synced" : "failed"}`}>
                Saved connection
              </span>
            )}
            {status.source === "environment" && (
              <span className="badge synced">Environment variables</span>
            )}
            {status.source === "none" && <span className="badge pending">Not configured</span>}
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            A connection saved on this page overrides the <code>ADO_ORG_URL</code>,{" "}
            <code>ADO_PAT</code> and <code>ADO_DEFAULT_PROJECT</code> environment variables as a
            whole. Remove it to go back to the environment variables.
          </p>
        </div>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <h2 style={{ marginTop: 0 }}>{stored ? "Saved connection" : "Save a connection"}</h2>
        <form onSubmit={save}>
          <div className="field">
            <label>Organization URL *</label>
            <input
              type="text"
              value={orgUrl}
              onChange={(e) => setOrgUrl(e.target.value)}
              placeholder={env?.org_url || "https://dev.azure.com/your-org"}
              required
            />
            <div className="help">
              Azure DevOps Services (https://dev.azure.com/org) or a Server collection URL.
            </div>
          </div>
          <div className="field">
            <label>Personal access token {stored ? "" : "*"}</label>
            <input
              type="password"
              value={pat}
              onChange={(e) => setPat(e.target.value)}
              placeholder={stored?.pat_set ? "Saved. Leave blank to keep it." : ""}
              autoComplete="new-password"
              required={!stored?.pat_set}
            />
            <div className="help">
              Needs Work Items (read &amp; write) and Project (read). Stored encrypted and never
              shown again.
            </div>
          </div>
          <div className="field">
            <label>Default project</label>
            <input
              type="text"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              // A saved connection never falls back to ADO_DEFAULT_PROJECT.
              placeholder={stored ? "" : env?.default_project || ""}
            />
            <div className="help">Used by portals that don't name a project.</div>
          </div>

          {test && (
            <div className={`alert ${test.ok ? "success" : "error"}`}>
              {test.ok
                ? `Connected. ${test.project_count} project(s) visible.`
                : `Connection failed: ${test.error}`}
            </div>
          )}

          <div className="row">
            <button className="btn" disabled={busy}>Save</button>
            <button
              type="button"
              className="btn secondary"
              onClick={testConnection}
              disabled={busy || !orgUrl || (!pat && !stored?.pat_set)}
            >
              Test connection
            </button>
            {stored && (
              <button type="button" className="btn danger" onClick={remove} disabled={busy}>
                Remove saved connection
              </button>
            )}
          </div>
          {stored && (
            <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>
              Last saved {new Date(stored.updated_at).toLocaleString()}
              {stored.updated_by ? ` by ${stored.updated_by}` : ""}.
            </div>
          )}
        </form>
      </div>

      {env && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Environment variables</h2>
          <table>
            <tbody>
              <tr>
                <td className="mono">ADO_ORG_URL</td>
                <td>{env.org_url || <span className="muted">not set</span>}</td>
              </tr>
              <tr>
                <td className="mono">ADO_PAT</td>
                <td>{env.pat_set ? "set" : <span className="muted">not set</span>}</td>
              </tr>
              <tr>
                <td className="mono">ADO_DEFAULT_PROJECT</td>
                <td>{env.default_project || <span className="muted">not set</span>}</td>
              </tr>
            </tbody>
          </table>
          {stored && (env.org_url || env.pat_set) && (
            <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>
              Ignored while a saved connection exists.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
