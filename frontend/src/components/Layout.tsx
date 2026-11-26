import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { isStaff } from "../auth/roles";
import { useAuth } from "../context/AuthContext";
import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // "/admin/tickets" is the Queue tab, not Admin.
  const inAdmin = pathname.startsWith("/admin") && !pathname.startsWith("/admin/tickets");

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <>
      <nav className="app-nav">
        <Link to="/" className="brand">
          <Logo size={30} />
          <span className="wordmark">Azuregos</span>
        </Link>
        <div className="links">
          <NavLink to="/" end>
            Browse
          </NavLink>
          <NavLink to="/tickets">My Tickets</NavLink>
          {isStaff(user) && (
            <NavLink to="/admin" className={() => (inAdmin ? "active" : "")}>
              Admin
            </NavLink>
          )}
          {isStaff(user) && <NavLink to="/admin/tickets">Queue</NavLink>}
          <NavLink to="/info">Info</NavLink>
        </div>
        <div className="spacer" />
        <span className="user">{user?.display_name || user?.email}</span>
        <ThemeToggle />
        <button className="btn secondary small" onClick={handleLogout}>
          Sign out
        </button>
      </nav>
      <Outlet />
    </>
  );
}
