import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Federated IdPs redirect here as /auth/callback#token=<jwt>
export default function AuthCallback() {
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const token = params.get("token");
    if (!token) {
      setError("No authentication token was returned.");
      return;
    }
    loginWithToken(token)
      .then(() => navigate("/", { replace: true }))
      .catch(() => setError("Failed to complete sign-in."));
  }, [loginWithToken, navigate]);

  return (
    <div className="center-screen muted">
      {error ? <div className="alert error">{error}</div> : "Completing sign-in…"}
    </div>
  );
}
