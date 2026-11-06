"""Integration framework: connector management (used by the API) and event dispatch/delivery (used by the worker).

Delivery protocol (for the receiving side see docs/integration.md):
  POST <endpoint_url>, Content-Type: application/json, body is the event JSON
  X-WMS-Event: event code; X-WMS-Event-Id: event ID (receivers deduplicate on it; unchanged on retries)
  X-WMS-Delivery: ID of this delivery job; X-WMS-Timestamp: Unix seconds
  X-WMS-Signature: sha256=HEX(HMAC_SHA256(secret, "<timestamp>.<body>"))
  A 2xx response means success; other status codes or timeouts are retried with backoff.
"""

import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import delete, false, func, select, true
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.event_catalog import EVENT_CODES, EVENT_TEST
from app.models.document import DocumentHeader
from app.models.integration import (
    EVENT_DISPATCHED,
    EVENT_NEW,
    EVENT_NO_SUBSCRIBER,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationJob,
    IntegrationLog,
    WorkerHeartbeat,
)
from app.models.tenant import Tenant
from app.repositories.base import check_version
from app.services.document_common import utcnow

# How long to wait before retrying after the nth failure (seconds); beyond the list the last value applies
RETRY_BACKOFF = [30, 120, 600, 1800, 3600, 7200, 14400]
# Lease for one call: if the worker crashes, another worker can take the job once the lease expires
LEASE_SECONDS = 120
WORKER_NAME = "integration"


def new_secret() -> str:
    return "whsec_" + secrets.token_hex(24)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _json_default(value):
    if isinstance(value, Decimal):
        # Quantities as numbers rather than strings, without trailing zeros
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        # Always UTC ending in Z; freshly created objects are tz-aware, ones read from the database are not (the database stores UTC)
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat(timespec="seconds") + "Z"
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


# ---------------------------------------------------------------- connector management


class ConnectorService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID | None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _validate(self, endpoint_url: str, event_types: list[str]) -> None:
        url = urlparse(endpoint_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise DomainError("The endpoint must be a full URL starting with http:// or https://")
        unknown = set(event_types) - EVENT_CODES
        if unknown:
            raise DomainError(f"Unknown events: {', '.join(sorted(unknown))}")

    def list(self) -> list[IntegrationConnector]:
        return list(
            self.db.scalars(
                select(IntegrationConnector)
                .where(IntegrationConnector.tenant_id == self.tenant_id, IntegrationConnector.is_deleted == false())
                .order_by(IntegrationConnector.code)
            )
        )

    def get(self, connector_id: uuid.UUID) -> IntegrationConnector:
        connector = self.db.get(IntegrationConnector, connector_id)
        if connector is None or connector.tenant_id != self.tenant_id or connector.is_deleted:
            raise NotFoundError("Connector not found")
        return connector

    def create(self, data) -> IntegrationConnector:
        self._validate(data.endpoint_url, data.event_types)
        connector = IntegrationConnector(
            tenant_id=self.tenant_id,
            code=data.code,
            name=data.name,
            endpoint_url=data.endpoint_url,
            secret=new_secret(),
            event_types=json.dumps(sorted(set(data.event_types))),
            extra_headers=json.dumps(data.extra_headers or {}, ensure_ascii=False),
            timeout_seconds=data.timeout_seconds,
            max_attempts=data.max_attempts,
            is_active=data.is_active,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.db.add(connector)
        self.db.flush()
        return connector

    def update(self, connector_id: uuid.UUID, data) -> IntegrationConnector:
        connector = self.get(connector_id)
        check_version(connector, data.row_version, f"Connector {connector.code}")
        self._validate(data.endpoint_url, data.event_types)
        connector.name = data.name
        connector.endpoint_url = data.endpoint_url
        connector.event_types = json.dumps(sorted(set(data.event_types)))
        connector.extra_headers = json.dumps(data.extra_headers or {}, ensure_ascii=False)
        connector.timeout_seconds = data.timeout_seconds
        connector.max_attempts = data.max_attempts
        connector.is_active = data.is_active
        connector.updated_by = self.user_id
        self.db.flush()
        return connector

    def delete(self, connector_id: uuid.UUID) -> None:
        connector = self.get(connector_id)
        connector.is_deleted = True
        connector.is_active = False
        connector.updated_by = self.user_id
        # Cancel jobs not yet delivered so a deleted connector is never called again
        for job in self.db.scalars(
            select(IntegrationJob).where(
                IntegrationJob.connector_id == connector.id, IntegrationJob.status == JOB_PENDING
            )
        ):
            job.status = JOB_FAILED
            job.last_error = "Connector deleted"
            job.completed_at = utcnow()
        self.db.flush()

    def rotate_secret(self, connector_id: uuid.UUID) -> IntegrationConnector:
        connector = self.get(connector_id)
        connector.secret = new_secret()
        connector.updated_by = self.user_id
        self.db.flush()
        return connector

    def send_test(self, connector_id: uuid.UUID) -> IntegrationJob:
        """Send a test event straight to this connector, bypassing subscriptions, to check the address and signature"""
        connector = self.get(connector_id)
        event = IntegrationEvent(
            tenant_id=self.tenant_id,
            event_type=EVENT_TEST,
            status=EVENT_DISPATCHED,
            created_by=self.user_id,
        )
        self.db.add(event)
        self.db.flush()
        event.payload = _envelope(self.db, event, {"message": "This is a test delivery; receiving it means the address and network work"})
        job = IntegrationJob(tenant_id=self.tenant_id, event_id=event.id, connector_id=connector.id)
        self.db.add(job)
        self.db.flush()
        return job

    # ---- job queries and manual handling

    def jobs(self, status: str | None, connector_id: uuid.UUID | None, event_type: str | None,
             doc_no: str | None, limit: int) -> list[IntegrationJob]:
        stmt = (
            select(IntegrationJob)
            .join(IntegrationJob.event)
            .where(IntegrationJob.tenant_id == self.tenant_id)
            .order_by(IntegrationJob.created_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(IntegrationJob.status == status)
        if connector_id:
            stmt = stmt.where(IntegrationJob.connector_id == connector_id)
        if event_type:
            stmt = stmt.where(IntegrationEvent.event_type == event_type)
        if doc_no:
            stmt = stmt.where(IntegrationEvent.doc_no == doc_no)
        return list(self.db.scalars(stmt).unique())

    def job(self, job_id: uuid.UUID) -> IntegrationJob:
        job = self.db.get(IntegrationJob, job_id)
        if job is None or job.tenant_id != self.tenant_id:
            raise NotFoundError("Job not found")
        return job

    def retry(self, job_id: uuid.UUID) -> IntegrationJob:
        job = self.job(job_id)
        if job.status not in (JOB_FAILED, JOB_PENDING):
            raise DomainError("Only failed or pending jobs can be redelivered")
        if not job.connector.is_active:
            raise DomainError("The connector is disabled; enable it before retrying")
        # Give it the full number of attempts again: manual intervention means the receiving side was fixed
        job.status = JOB_PENDING
        job.attempts = 0
        job.next_attempt_at = utcnow()
        job.completed_at = None
        job.updated_by = self.user_id
        self.db.flush()
        return job

    def summary(self) -> dict:
        counts = dict(
            self.db.execute(
                select(IntegrationJob.status, func.count())
                .where(IntegrationJob.tenant_id == self.tenant_id)
                .group_by(IntegrationJob.status)
            ).all()
        )
        heartbeat = self.db.get(WorkerHeartbeat, WORKER_NAME)
        return {
            "jobs": {s: counts.get(s, 0) for s in (JOB_PENDING, JOB_RUNNING, JOB_SUCCEEDED, JOB_FAILED)},
            "worker_last_seen": heartbeat.last_seen if heartbeat else None,
        }


# ---------------------------------------------------------------- payload


def _envelope(db: Session, event: IntegrationEvent, data: dict) -> str:
    tenant = db.get(Tenant, event.tenant_id)
    return json.dumps(
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
            "tenant": tenant.code if tenant else None,
            "data": data,
        },
        ensure_ascii=False,
        default=_json_default,
    )


def document_payload(doc: DocumentHeader) -> dict:
    """Document content pushed to external systems: business codes instead of internal IDs, receivers do not need our keys"""

    def loc(location):
        return location.code if location else None

    return {
        "doc_type": doc.doc_type,
        "doc_no": doc.doc_no,
        "status": doc.status,
        "partner": {"code": doc.partner.code, "name": doc.partner.name} if doc.partner else None,
        "ref_document": {"doc_type": doc.ref_document.doc_type, "doc_no": doc.ref_document.doc_no}
        if doc.ref_document
        else None,
        "reason_code": doc.reason_code.code if doc.reason_code else None,
        "expected_date": doc.expected_date,
        "posted_at": doc.posted_at,
        "remark": doc.remark,
        "lines": [
            {
                "line_no": line.line_no,
                "sku": line.item.sku_code,
                "item_name": line.item.name,
                "uom": line.uom.code,
                "qty_planned": line.qty_planned,
                "qty_actual": line.qty_actual,
                "batch_no": line.batch_no,
                "expiry_date": line.expiry_date,
                "from_location": loc(line.from_location),
                "to_location": loc(line.to_location),
            }
            for line in doc.lines
        ],
    }


# ---------------------------------------------------------------- worker


def dispatch_events(db: Session, batch: int = 100) -> int:
    """Turn new events into delivery jobs per subscription. READPAST: several workers each take their own rows without waiting on each other."""
    events = list(
        db.scalars(
            select(IntegrationEvent)
            .with_hint(IntegrationEvent, "WITH (UPDLOCK, READPAST, ROWLOCK)", "mssql")
            .where(IntegrationEvent.status == EVENT_NEW)
            .order_by(IntegrationEvent.created_at)
            .limit(batch)
        )
    )
    if not events:
        return 0
    connectors: dict[uuid.UUID, list[IntegrationConnector]] = {}
    for event in events:
        if event.tenant_id not in connectors:
            connectors[event.tenant_id] = list(
                db.scalars(
                    select(IntegrationConnector).where(
                        IntegrationConnector.tenant_id == event.tenant_id,
                        IntegrationConnector.is_active == true(),
                        IntegrationConnector.is_deleted == false(),
                    )
                )
            )
        targets = [c for c in connectors[event.tenant_id] if event.event_type in json.loads(c.event_types)]
        if not targets:
            event.status = EVENT_NO_SUBSCRIBER
            continue
        doc = db.get(DocumentHeader, event.document_id) if event.document_id else None
        event.payload = _envelope(db, event, document_payload(doc) if doc else {})
        event.status = EVENT_DISPATCHED
        for connector in targets:
            db.add(IntegrationJob(tenant_id=event.tenant_id, event_id=event.id, connector_id=connector.id))
    db.commit()
    return len(events)


def claim_jobs(db: Session, batch: int = 20) -> list[uuid.UUID]:
    now = utcnow()
    jobs = list(
        db.scalars(
            select(IntegrationJob)
            .with_hint(IntegrationJob, "WITH (UPDLOCK, READPAST, ROWLOCK)", "mssql")
            .where(
                (
                    (IntegrationJob.status == JOB_PENDING) & (IntegrationJob.next_attempt_at <= now)
                )
                # The previous worker took the job and crashed: take it again once the lease has expired
                | ((IntegrationJob.status == JOB_RUNNING) & (IntegrationJob.locked_until < now))
            )
            .order_by(IntegrationJob.next_attempt_at)
            .limit(batch)
        )
    )
    for job in jobs:
        job.status = JOB_RUNNING
        job.locked_until = now + timedelta(seconds=LEASE_SECONDS)
    ids = [job.id for job in jobs]
    db.commit()
    return ids


def _post(target: dict, job_id: uuid.UUID) -> tuple[int | None, str | None, str | None]:
    """Return (status code, first 2000 characters of the response body, error description); never raises"""
    body = target["payload"].encode("utf-8")
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "WMS-Integration/1.0",
        "X-WMS-Event": target["event_type"],
        "X-WMS-Event-Id": target["event_id"],
        "X-WMS-Delivery": str(job_id),
        "X-WMS-Timestamp": timestamp,
        "X-WMS-Signature": sign(target["secret"], timestamp, body),
        **target["headers"],
    }
    request = urllib.request.Request(target["url"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=target["timeout"]) as response:
            return response.status, response.read(2000).decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2000).decode("utf-8", "replace"), f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - network errors, timeouts, DNS failures are all retried
        return None, None, f"{type(exc).__name__}: {exc}"[:1000]


def deliver(db: Session, job_id: uuid.UUID) -> bool:
    """Call the external system once. The HTTP call happens outside a database transaction so a slow receiver does not hold locks."""
    job = db.get(IntegrationJob, job_id)
    connector, event = job.connector, job.event
    active = connector.is_active and not connector.is_deleted
    # ORM objects expire after commit, so take the values needed for the call first
    target = {
        "url": connector.endpoint_url,
        "secret": connector.secret,
        "headers": json.loads(connector.extra_headers or "{}"),
        "timeout": connector.timeout_seconds,
        "payload": event.payload or "{}",
        "event_type": event.event_type,
        "event_id": str(event.id),
    }
    max_attempts = connector.max_attempts
    db.commit()

    started = utcnow()
    clock = time.monotonic()
    if active:
        status_code, response_body, error = _post(target, job_id)
    else:
        status_code, response_body, error = None, None, "Connector disabled"
    duration_ms = int((time.monotonic() - clock) * 1000)
    success = error is None and status_code is not None and 200 <= status_code < 300

    job = db.get(IntegrationJob, job_id, populate_existing=True)
    job.attempts += 1
    # Log numbers increase over the job's lifetime; a manual retry resets attempts (full retry budget), so attempts cannot be the number
    log_no = (db.scalar(select(func.max(IntegrationLog.attempt_no)).where(IntegrationLog.job_id == job.id)) or 0) + 1
    db.add(
        IntegrationLog(
            tenant_id=job.tenant_id,
            job_id=job.id,
            attempt_no=log_no,
            requested_at=started,
            duration_ms=duration_ms,
            status_code=status_code,
            success=success,
            error=error,
            response_body=response_body,
        )
    )
    job.last_status_code = status_code
    job.locked_until = None
    if success:
        job.status = JOB_SUCCEEDED
        job.last_error = None
        job.completed_at = utcnow()
    elif job.attempts >= max_attempts or not active:
        job.status = JOB_FAILED
        job.last_error = error
        job.completed_at = utcnow()
    else:
        job.status = JOB_PENDING
        job.last_error = error
        wait = RETRY_BACKOFF[min(job.attempts - 1, len(RETRY_BACKOFF) - 1)]
        job.next_attempt_at = utcnow() + timedelta(seconds=wait)
    db.commit()
    return success


def heartbeat(db: Session, info: str) -> None:
    row = db.get(WorkerHeartbeat, WORKER_NAME)
    if row is None:
        db.add(WorkerHeartbeat(name=WORKER_NAME, last_seen=utcnow(), info=info))
    else:
        row.last_seen = utcnow()
        row.info = info
    db.commit()


def purge(db: Session, retention_days: int) -> int:
    """Purge old records: finished jobs with their logs and processed events. Failed and unfinished ones stay for manual handling."""
    cutoff = utcnow() - timedelta(days=retention_days)
    old_jobs = select(IntegrationJob.id).where(
        IntegrationJob.status == JOB_SUCCEEDED, IntegrationJob.completed_at < cutoff
    )
    db.execute(delete(IntegrationLog).where(IntegrationLog.job_id.in_(old_jobs)))
    removed = db.execute(delete(IntegrationJob).where(IntegrationJob.id.in_(old_jobs))).rowcount
    open_events = select(IntegrationJob.event_id)
    db.execute(
        delete(IntegrationEvent).where(
            IntegrationEvent.status != EVENT_NEW,
            IntegrationEvent.created_at < cutoff,
            IntegrationEvent.id.not_in(open_events),
        )
    )
    db.commit()
    return removed or 0
