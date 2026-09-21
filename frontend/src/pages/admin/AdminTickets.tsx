import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import StatusBadge from "../../components/StatusBadge";
import type { Portal, SyncStatus, TicketListItem } from "../../types";

const STATUS_FILTERS: Array<{ value: SyncStatus | "all"; label: string }> = [
  { value: "all", label: "All" },
  { value: "pending", label: "Queued" },
  { value: "failed", label: "Needs attention" },
  { value: "synced", label: "Submitted" },
  { value: "syncing", label: "Syncing" },
];

export default function AdminTickets() {
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [portals, setPortals] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<SyncStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get<TicketListItem[]>("/api/tickets?all_tickets=true"),
      api.get<Portal[]>("/api/portals"),
    ])
      .then(([ts, ps]) => {
        setTickets(ts);
        setPortals(Object.fromEntries(ps.map((p) => [p.id, p.name])));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const retry = async (id: string) => {
    setRetrying(id);
    setError(null);
    try {
      await api.post(`/api/tickets/${id}/retry`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Retry failed");
    } finally {
      setRetrying(null);
    }
  };

  const visible = useMemo(
    () => (filter === "all" ? tickets : tickets.filter((t) => t.sync_status === filter)),
    [tickets, filter],
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const t of tickets) c[t.sync_status] = (c[t.sync_status] || 0) + 1;
    return c;
  }, [tickets]);

  return (
    <div className="container">
      <div className="row between">
        <div>
          <h1>Ticket Queue</h1>
          <p className="subtitle">All requests submitted across every portal.</p>
        </div>
        <button className="btn secondary" onClick={load}>
          Refresh
        </button>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="row" style={{ marginBottom: 16 }}>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            className={`btn small ${filter === f.value ? "" : "secondary"}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
            {f.value !== "all" && counts[f.value] ? ` (${counts[f.value]})` : ""}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="muted">Loading…</div>
      ) : visible.length === 0 ? (
        <div className="empty">No tickets{filter !== "all" ? " with this status" : ""}.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Submitter</th>
                <th>Portal</th>
                <th>Status</th>
                <th>ADO</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => (
                <tr key={t.id}>
                  <td
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/tickets/${t.id}`)}
                  >
                    {t.title}
                  </td>
                  <td className="muted">{t.submitter_email}</td>
                  <td>{portals[t.portal_id] || "—"}</td>
                  <td>
                    <StatusBadge status={t.sync_status} />
                  </td>
                  <td>
                    {t.ado_url ? (
                      <a href={t.ado_url} target="_blank" rel="noreferrer" className="mono">
                        #{t.ado_work_item_id}
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                    {t.ado_state && <span className="tag" style={{ marginLeft: 6 }}>{t.ado_state}</span>}
                  </td>
                  <td className="muted">{new Date(t.created_at).toLocaleDateString()}</td>
                  <td>
                    {(t.sync_status === "pending" || t.sync_status === "failed") && (
                      <button
                        className="btn secondary small"
                        disabled={retrying === t.id}
                        onClick={() => retry(t.id)}
                      >
                        {retrying === t.id ? "Retrying…" : "Retry"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
