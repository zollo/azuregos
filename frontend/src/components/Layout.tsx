import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <>
      <nav className="app-nav">
        <Link to="/" className="brand">
          Azure<span>gos</span>
        </Link>
        <div className="links">
          <Link to="/">Browse</Link>
          <Link to="/tickets">My Tickets</Link>
          {user?.role === "admin" && <Link to="/admin">Admin</Link>}
        </div>
        <div className="spacer" />
        <span className="user">{user?.display_name || user?.email}</span>
        <button className="btn secondary small" onClick={handleLogout}>
          Sign out
        </button>
      </nav>
      <Outlet />
    </>
  );
}
