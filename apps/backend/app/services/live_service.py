"""Live change feed for the web console (server-sent events, see app/api/v1/events.py).

The audit log is the source: every committed change to business data already has a row there (app/models/audit.py),
written in the same transaction. Each backend process runs one poller, only while it has connected browsers, that
reads new audit rows for the tenants it serves and fans them out to those browsers. Several processes or servers
need no shared broker: each reads the same table.

Events say only what changed (record type, id, action), never values or labels: the browser uses them to know which
data to refetch through the normal, permission-checked API.

Rows become visible when their transaction commits, which can be after rows written later by faster transactions,
so every poll looks back OVERLAP and skips rows it has already sent.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.audit import AuditLog
from app.models.document import DocumentHeader
from app.services.document_common import utcnow

log = logging.getLogger(__name__)

POLL_SECONDS = 1.5
OVERLAP = timedelta(seconds=30)
MAX_ROWS_PER_POLL = 1000
QUEUE_SIZE = 500
# Sent instead of individual events when a browser falls behind or a burst exceeds one poll: refetch everything
RESYNC = {"type": "resync"}


@dataclass
class _TenantState:
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    # When the first browser of this tenant subscribed: earlier changes are not replayed, later ones always sent
    since: datetime = field(default_factory=utcnow)
    primed: bool = False
    seen: dict[uuid.UUID, datetime] = field(default_factory=dict)


class ChangeFeed:
    def __init__(self, poll_seconds: float = POLL_SECONDS):
        self.poll_seconds = poll_seconds
        self._tenants: dict[uuid.UUID, _TenantState] = {}
        self._task: asyncio.Task | None = None

    def subscribe(self, tenant_id: uuid.UUID) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._tenants.setdefault(tenant_id, _TenantState()).subscribers.add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="live-change-feed")
        return queue

    def unsubscribe(self, tenant_id: uuid.UUID, queue: asyncio.Queue) -> None:
        state = self._tenants.get(tenant_id)
        if state is None:
            return
        state.subscribers.discard(queue)
        if not state.subscribers:
            del self._tenants[tenant_id]

    @property
    def subscriber_count(self) -> int:
        return sum(len(s.subscribers) for s in self._tenants.values())

    async def _run(self) -> None:
        while self._tenants:
            try:
                batches = await asyncio.to_thread(self.poll_once)
                for tenant_id, events in batches.items():
                    state = self._tenants.get(tenant_id)
                    for queue in list(state.subscribers if state else ()):
                        _deliver(queue, events)
            except Exception:  # noqa: BLE001 - a database hiccup must not end the feed; try again next round
                log.exception("Live change feed poll failed")
            await asyncio.sleep(self.poll_seconds)

    def poll_once(self) -> dict[uuid.UUID, list[dict]]:
        """New changes per tenant since the last poll (runs in a worker thread: the database driver is synchronous)"""
        result: dict[uuid.UUID, list[dict]] = {}
        with SessionLocal() as db:
            for tenant_id, state in list(self._tenants.items()):
                subscribed_at, priming = state.since, not state.primed
                state.primed = True
                rows = list(
                    db.execute(
                        select(
                            AuditLog.id, AuditLog.occurred_at, AuditLog.entity_type, AuditLog.entity_id,
                            AuditLog.parent_id, AuditLog.action, AuditLog.entity_label,
                        )
                        .where(AuditLog.tenant_id == tenant_id, AuditLog.occurred_at >= state.since - OVERLAP)
                        .order_by(AuditLog.occurred_at)
                        .limit(MAX_ROWS_PER_POLL)
                    )
                )
                fresh = [r for r in rows if r.id not in state.seen]
                for r in fresh:
                    state.seen[r.id] = r.occurred_at
                if priming:
                    # First poll: what happened before the subscription is history, not news
                    fresh = [r for r in fresh if r.occurred_at >= subscribed_at]
                if rows:
                    state.since = max(state.since, rows[-1].occurred_at)
                cutoff = state.since - OVERLAP
                state.seen = {k: v for k, v in state.seen.items() if v >= cutoff}
                if len(rows) == MAX_ROWS_PER_POLL:
                    result[tenant_id] = [RESYNC]
                elif fresh:
                    result[tenant_id] = _events(db, fresh)
        return result


def _events(db, rows) -> list[dict]:
    """Collapse to one event per record, and name the document type of document children (lines, count entries)"""
    parent_ids = {r.parent_id for r in rows if r.parent_id}
    doc_types = dict(
        db.execute(select(DocumentHeader.id, DocumentHeader.doc_type).where(DocumentHeader.id.in_(parent_ids))).all()
    ) if parent_ids else {}
    events: dict[tuple, dict] = {}
    for r in rows:
        doc_type = None
        if r.entity_type == "document" and r.entity_label:
            doc_type = r.entity_label.split(" ")[0]  # label is "<doc type> <doc no>"
        elif r.parent_id:
            doc_type = doc_types.get(r.parent_id)
        events[(r.entity_type, r.entity_id)] = {
            "type": r.entity_type,
            "id": str(r.entity_id),
            "parent_id": str(r.parent_id) if r.parent_id else None,
            "action": r.action,
            "doc_type": doc_type,
        }
    return list(events.values())


def _deliver(queue: asyncio.Queue, events: list[dict]) -> None:
    for event in events:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # The browser is not reading fast enough: drop the backlog and tell it to refetch everything
            with contextlib.suppress(asyncio.QueueEmpty):
                while True:
                    queue.get_nowait()
            queue.put_nowait(RESYNC)
            return


feed = ChangeFeed()
