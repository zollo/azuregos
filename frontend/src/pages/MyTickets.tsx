import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import type { TicketListItem } from "../types";

export default function MyTickets() {
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get<TicketListItem[]>("/api/tickets")
      .then(setTickets)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="container muted">Loading tickets…</div>;

  return (
    <div className="container">
      <h1>My Tickets</h1>
      <p className="subtitle">Requests you have submitted and their status.</p>

      {tickets.length === 0 ? (
        <div className="empty">
          You haven&apos;t submitted any requests yet.
          <br />
          <a onClick={() => navigate("/")} style={{ cursor: "pointer" }}>
            Browse portals →
          </a>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>ADO State</th>
                <th>Work Item</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => navigate(`/tickets/${t.id}`)}
                  style={{ cursor: "pointer" }}
                >
                  <td>{t.title}</td>
                  <td>
                    <StatusBadge status={t.sync_status} />
                  </td>
                  <td className="muted">{t.ado_state || "—"}</td>
                  <td>
                    {t.ado_work_item_id ? (
                      <span className="mono">#{t.ado_work_item_id}</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="muted">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
