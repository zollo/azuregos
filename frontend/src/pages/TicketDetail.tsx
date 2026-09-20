import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import type { Ticket } from "../types";

export default function TicketDetail() {
  const { id } = useParams();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api
      .get<Ticket>(`/api/tickets/${id}?refresh=true`)
      .then(setTicket)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="container muted">Loading…</div>;
  if (!ticket) return <div className="container"><div className="alert error">Ticket not found.</div></div>;

  const values = Object.entries(ticket.field_values);

  return (
    <div className="container narrow">
      <div className="breadcrumb">
        <Link to="/tickets">← My Tickets</Link>
      </div>
      <div className="row between">
        <h1 style={{ marginBottom: 0 }}>{ticket.title}</h1>
        <StatusBadge status={ticket.sync_status} />
      </div>
      <p className="subtitle" style={{ marginTop: 8 }}>
        Submitted {new Date(ticket.created_at).toLocaleString()}
      </p>

      {ticket.sync_status === "pending" && (
        <div className="alert info">
          This request is queued and will be sent to the service team automatically.
          It hasn&apos;t reached Azure DevOps yet.
        </div>
      )}
      {ticket.sync_status === "failed" && (
        <div className="alert error">
          We&apos;re having trouble delivering this request. The team has been notified and
          it will keep retrying.
        </div>
      )}

      <div className="card">
        {ticket.description && (
          <div className="field">
            <label>Discussion</label>
            <div>{ticket.description}</div>
          </div>
        )}

        {values.length > 0 && (
          <>
            <hr className="divider" />
            {values.map(([k, v]) => (
              <div className="field" key={k}>
                <label>{k}</label>
                <div>{Array.isArray(v) ? v.join(", ") : String(v)}</div>
              </div>
            ))}
          </>
        )}

        <hr className="divider" />
        <div className="row between">
          <div>
            <div className="muted" style={{ fontSize: 13 }}>Azure DevOps</div>
            {ticket.ado_work_item_id ? (
              <span className="mono">Work item #{ticket.ado_work_item_id}</span>
            ) : (
              <span className="muted">Not yet created</span>
            )}
            {ticket.ado_state && <span className="tag" style={{ marginLeft: 8 }}>{ticket.ado_state}</span>}
          </div>
          {ticket.ado_url && (
            <a className="btn secondary small" href={ticket.ado_url} target="_blank" rel="noreferrer">
              Open in ADO ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
