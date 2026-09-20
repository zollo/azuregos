import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import AuthCallback from "./pages/AuthCallback";
import Catalog from "./pages/Catalog";
import Login from "./pages/Login";
import MyTickets from "./pages/MyTickets";
import PortalForm from "./pages/PortalForm";
import Register from "./pages/Register";
import TicketDetail from "./pages/TicketDetail";
import AdminCategories from "./pages/admin/AdminCategories";
import AdminPortalEditor from "./pages/admin/AdminPortalEditor";
import AdminPortals from "./pages/admin/AdminPortals";
import AdminUsers from "./pages/admin/AdminUsers";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/callback" element={<AuthCallback />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Catalog />} />
        <Route path="/portals/:slug" element={<PortalForm />} />
        <Route path="/tickets" element={<MyTickets />} />
        <Route path="/tickets/:id" element={<TicketDetail />} />
      </Route>

      <Route
        element={
          <ProtectedRoute adminOnly>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/admin" element={<AdminPortals />} />
        <Route path="/admin/portals/new" element={<AdminPortalEditor />} />
        <Route path="/admin/portals/:id" element={<AdminPortalEditor />} />
        <Route path="/admin/categories" element={<AdminCategories />} />
        <Route path="/admin/users" element={<AdminUsers />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
