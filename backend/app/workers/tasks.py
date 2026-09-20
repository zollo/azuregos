"""Background tasks. The key one drains the offline ticket cache into ADO."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db import create_worker_engine
from app.models.ticket import SyncStatus, Ticket
from app.services.ado_client import ADOError
from app.services.ticket_service import push_ticket_to_ado
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _drain() -> dict:
    """Attempt to push every eligible pending ticket to ADO."""
    pushed, failed, skipped = 0, 0, 0
    engine, session_factory = create_worker_engine()
    try:
        async with session_factory() as db:
            tickets = await _drain_session(db)
            for ticket in tickets:
                try:
                    await push_ticket_to_ado(db, ticket)
                    pushed += 1
                except ADOError as exc:
                    failed += 1
                    logger.warning("Ticket %s still failing: %s", ticket.id, exc)
                except Exception:  # noqa: BLE001
                    skipped += 1
                    logger.exception("Unexpected error syncing ticket %s", ticket.id)
    finally:
        await engine.dispose()

    return {"pushed": pushed, "failed": failed, "skipped": skipped, "found": len(tickets)}


async def _drain_session(db) -> list[Ticket]:
    """Select the eligible pending tickets to attempt this cycle."""
    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.sync_status == SyncStatus.pending,
            Ticket.ado_work_item_id.is_(None),
            Ticket.sync_attempts < settings.ado_max_retry_attempts,
        )
        .order_by(Ticket.created_at)
        .limit(100)
    )
    return list(result.scalars().all())


@celery_app.task(name="app.workers.tasks.retry_pending_tickets")
def retry_pending_tickets() -> dict:
    """Celery entrypoint: run the async drain in a fresh event loop."""
    summary = asyncio.run(_drain())
    if summary["found"]:
        logger.info("Retry loop: %s", summary)
    return summary
