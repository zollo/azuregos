import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await register(email, password, displayName);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-screen">
      <div className="card" style={{ width: 400 }}>
        <h1>Create an account</h1>
        <p className="subtitle">Register to start submitting requests.</p>
        {error && <div className="alert error">{error}</div>}
        <form onSubmit={submit}>
          <div className="field">
            <label>Full name</label>
            <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
            />
            <div className="help">At least 8 characters.</div>
          </div>
          <button className="btn" style={{ width: "100%" }} disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: 18, textAlign: "center" }}>
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
