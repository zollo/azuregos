import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import type { Ticket, TicketComment } from "../types";

export default function TicketDetail() {
  const { id } = useParams();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);

  const [comments, setComments] = useState<TicketComment[]>([]);
  const [reply, setReply] = useState("");
  const [posting, setPosting] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);

  const loadComments = useCallback(async () => {
    if (!id) return;
    try {
      setComments(await api.get<TicketComment[]>(`/api/tickets/${id}/comments`));
    } catch {
      /* discussion is best-effort; ignore load errors */
    }
  }, [id]);

  useEffect(() => {
    if (!id) return;
    api
      .get<Ticket>(`/api/tickets/${id}?refresh=true`)
      .then((t) => {
        setTicket(t);
        if (t.ado_work_item_id) void loadComments();
      })
      .finally(() => setLoading(false));
  }, [id, loadComments]);

  const submitReply = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !reply.trim()) return;
    setCommentError(null);
    setPosting(true);
    try {
      await api.post(`/api/tickets/${id}/comments`, { text: reply });
      setReply("");
      await loadComments();
    } catch (err) {
      setCommentError(err instanceof ApiError ? err.message : "Failed to post reply");
    } finally {
      setPosting(false);
    }
  };

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

      {/* Discussion */}
      <h2>Discussion</h2>
      {!ticket.ado_work_item_id ? (
        <div className="alert info">
          The discussion will be available once your request reaches the service desk.
        </div>
      ) : (
        <div className="card">
          {comments.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>No replies yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {comments.map((c) => (
                <div key={c.id}>
                  <div className="row between">
                    <strong>{c.author}</strong>
                    <span className="muted" style={{ fontSize: 13 }}>
                      {new Date(c.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{c.text}</div>
                </div>
              ))}
            </div>
          )}

          <hr className="divider" />
          {commentError && <div className="alert error">{commentError}</div>}
          <form onSubmit={submitReply}>
            <div className="field" style={{ marginBottom: 10 }}>
              <label htmlFor="reply">Add a reply</label>
              <textarea
                id="reply"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Write a reply to the service desk…"
              />
            </div>
            <button className="btn" disabled={posting || !reply.trim()}>
              {posting ? "Posting…" : "Post reply"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
