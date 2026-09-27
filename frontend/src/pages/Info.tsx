import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { BuildInfo } from "../types";

const REPO_URL = "https://github.com/zollo/azuregos";

function shortSha(sha: string): string {
  return /^[0-9a-f]{40}$/i.test(sha) ? sha.slice(0, 7) : sha;
}

function commitLink(sha: string) {
  if (!/^[0-9a-f]{7,40}$/i.test(sha)) return <span className="mono">{sha}</span>;
  return (
    <a className="mono" href={`${REPO_URL}/commit/${sha}`} target="_blank" rel="noreferrer">
      {shortSha(sha)} ↗
    </a>
  );
}

function fmtTime(t: string): string {
  if (!t || t === "unknown") return "unknown";
  const d = new Date(t);
  return isNaN(d.getTime()) ? t : d.toLocaleString();
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="row between" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <span className="muted">{label}</span>
      <span>{children}</span>
    </div>
  );
}

export default function Info() {
  const [backend, setBackend] = useState<BuildInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fe = {
    version: import.meta.env.VITE_APP_VERSION || "dev",
    git_commit: import.meta.env.VITE_GIT_COMMIT || "unknown",
    build_time: import.meta.env.VITE_BUILD_TIME || "unknown",
  };

  useEffect(() => {
    api
      .get<BuildInfo>("/api/build-info")
      .then(setBackend)
      .catch(() => setError("Could not load API build info."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="container narrow">
      <h1>Build Information</h1>
      <p className="subtitle">Details about the currently running version of Azuregos.</p>

      <h2>Frontend</h2>
      <div className="card">
        <Row label="Version"><span className="mono">{fe.version}</span></Row>
        <Row label="Commit">{commitLink(fe.git_commit)}</Row>
        <Row label="Built">{fmtTime(fe.build_time)}</Row>
      </div>

      <h2>API</h2>
      {loading ? (
        <div className="muted">Loading…</div>
      ) : error ? (
        <div className="alert error">{error}</div>
      ) : backend ? (
        <div className="card">
          <Row label="Version"><span className="mono">{backend.version}</span></Row>
          <Row label="Commit">{commitLink(backend.git_commit)}</Row>
          <Row label="Built">{fmtTime(backend.build_time)}</Row>
          <Row label="Environment"><span className="tag">{backend.environment}</span></Row>
          <Row label="Azure DevOps">
            <span className={`badge ${backend.ado_configured ? "synced" : "pending"}`}>
              {backend.ado_configured ? "Configured" : "Not configured"}
            </span>
          </Row>
        </div>
      ) : null}
    </div>
  );
}
