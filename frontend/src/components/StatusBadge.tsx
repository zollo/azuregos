import type { SyncStatus } from "../types";

const LABELS: Record<SyncStatus, string> = {
  pending: "Queued",
  syncing: "Syncing",
  synced: "Submitted",
  failed: "Needs attention",
};

// Shows the sync state of a ticket relative to Azure DevOps.
export default function StatusBadge({ status }: { status: SyncStatus }) {
  return <span className={`badge ${status}`}>{LABELS[status]}</span>;
}
