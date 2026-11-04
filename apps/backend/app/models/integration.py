"""Integration framework (PLAN 4.5): one set of connectors / events / delivery jobs / call logs, replacing Ninso's ApiLog table per document type.

Flow (outbox pattern): document status change -> integration_event written in the same transaction -> the worker (app/worker.py)
creates an integration_job per subscribed connector -> calls the external system, writing integration_log for every call and retrying failures with backoff.
If the business transaction rolls back the event rolls back too, so nothing is pushed for something that did not happen.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.event_catalog import EVENT_BY_STATUS
from app.models.base import Base, TenantScopedMixin, _utcnow
from app.models.document import DocumentHeader

CONNECTOR_WEBHOOK = "WEBHOOK"

EVENT_NEW = "NEW"  # waiting for the worker to dispatch
EVENT_DISPATCHED = "DISPATCHED"  # jobs created for subscribed connectors
EVENT_NO_SUBSCRIBER = "NO_SUBSCRIBER"  # no connector subscribed, nothing to push

JOB_PENDING = "PENDING"  # waiting for its (first or next) call
JOB_RUNNING = "RUNNING"  # a worker is calling it (no other worker takes it before locked_until)
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"  # retries exhausted; needs manual handling and a manual retry


class IntegrationConnector(Base, TenantScopedMixin):
    """External system connection. Only Webhook for now (POST JSON to an address the receiver provides);
    ERP-specific connectors (SAP, Yonyou, Kingdee) can be added as new connector_type values when a customer needs them, without schema changes."""

    __tablename__ = "integration_connector"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(Unicode(30), default=CONNECTOR_WEBHOOK, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    # Signing secret: receivers use it to verify requests really come from this system (HMAC-SHA256)
    secret: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    # Subscribed event codes, JSON array
    event_types: Mapped[str] = mapped_column(UnicodeText, default="[]", nullable=False)
    # Extra request headers (e.g. an Authorization the receiver requires), JSON object
    extra_headers: Mapped[str] = mapped_column(UnicodeText, default="{}", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class IntegrationEvent(Base, TenantScopedMixin):
    __tablename__ = "integration_event"
    __table_args__ = (Index("ix_integration_event_status", "status", "created_at"),)

    event_type: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    status: Mapped[str] = mapped_column(Unicode(20), default=EVENT_NEW, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_header.id"), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    doc_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    # Payload snapshot: built once at dispatch, so every retry sends the same content
    payload: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class IntegrationJob(Base, TenantScopedMixin):
    __tablename__ = "integration_job"
    __table_args__ = (Index("ix_integration_job_due", "status", "next_attempt_at"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_event.id"), index=True, nullable=False)
    connector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_connector.id"), nullable=False)
    status: Mapped[str] = mapped_column(Unicode(20), default=JOB_PENDING, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped[IntegrationEvent] = relationship(lazy="joined")
    connector: Mapped[IntegrationConnector] = relationship(lazy="joined")
    logs: Mapped[list["IntegrationLog"]] = relationship(
        order_by="IntegrationLog.attempt_no", lazy="selectin", cascade="all, delete-orphan"
    )


class IntegrationLog(Base, TenantScopedMixin):
    __tablename__ = "integration_log"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_job.id"), index=True, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    response_body: Mapped[str | None] = mapped_column(Unicode(2000), nullable=True)


class WorkerHeartbeat(Base):
    """Background worker heartbeat: the UI uses it to warn that the worker is not running so jobs do not pile up silently. System-wide, not per tenant."""

    __tablename__ = "worker_heartbeat"

    name: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    info: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)


@event.listens_for(Session, "before_flush")
def _record_document_events(session: Session, _flush_context, _instances) -> None:
    """When a document's status changes to a registered status, write an event in the same transaction (outbox)."""
    for obj in (*session.new, *session.dirty):
        if not isinstance(obj, DocumentHeader):
            continue
        history = inspect(obj).attrs.status.history
        if not history.added:
            continue
        old = history.deleted[0] if history.deleted else None
        event_type = EVENT_BY_STATUS.get((obj.doc_type, obj.status))
        if event_type is None or obj.status == old:
            continue
        if obj.id is None:  # a new document gets its primary key at flush; assign it now
            obj.id = uuid.uuid4()
        session.add(
            IntegrationEvent(
                tenant_id=obj.tenant_id,
                event_type=event_type,
                document_id=obj.id,
                doc_type=obj.doc_type,
                doc_no=obj.doc_no,
                created_by=obj.updated_by,
            )
        )
