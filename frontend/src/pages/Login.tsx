import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { AuthProviders } from "../types";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<AuthProviders>({
    local: true,
    oidc: false,
    saml: false,
  });

  useEffect(() => {
    if (user) navigate("/");
  }, [user, navigate]);

  useEffect(() => {
    api.get<AuthProviders>("/api/auth/providers").then(setProviders).catch(() => {});
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-screen">
      <div className="card" style={{ width: 400 }}>
        <h1 style={{ color: "var(--primary)" }}>
          Azure<span style={{ color: "var(--text)" }}>gos</span>
        </h1>
        <p className="subtitle">Sign in to submit and track your requests.</p>

        {error && <div className="alert error">{error}</div>}

        <form onSubmit={submit}>
          <div className="field">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn" style={{ width: "100%" }} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {(providers.oidc || providers.saml) && (
          <>
            <hr className="divider" />
            <div className="row" style={{ flexDirection: "column", gap: 8 }}>
              {providers.oidc && (
                <a className="btn secondary" style={{ width: "100%", justifyContent: "center" }}
                   href={`${api.baseUrl}/api/auth/oidc/login`}>
                  Continue with SSO (OIDC)
                </a>
              )}
              {providers.saml && (
                <a className="btn secondary" style={{ width: "100%", justifyContent: "center" }}
                   href={`${api.baseUrl}/api/auth/saml/login`}>
                  Continue with SSO (SAML)
                </a>
              )}
            </div>
          </>
        )}

        <p className="muted" style={{ marginTop: 18, textAlign: "center" }}>
          No account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
