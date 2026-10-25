import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { hasAccess, type AdminAccess } from "../auth/roles";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({
  children,
  access,
}: {
  children: ReactNode;
  /** Restrict to an admin role; omit for any signed-in user. */
  access?: AdminAccess;
}) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="center-screen muted">Loading…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (access && !hasAccess(user, access)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
