"""Operational status for the System > Health page. Everything comes from the database, so the answer is the same
whichever backend process serves the request (production runs several)."""

import time
import uuid
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.integration import JOB_FAILED, JOB_PENDING, JOB_RUNNING, IntegrationJob, WorkerHeartbeat
from app.schemas.system import (
    DatabaseStatus,
    IntegrationQueueStatus,
    SystemStatus,
    TableSize,
    TelemetryStatus,
    WorkerStatus,
)
from app.services.document_common import utcnow
from app.services.integration_service import WORKER_NAME

# The worker writes its heartbeat every few seconds; this long without one means it is not running
WORKER_STALE_AFTER = timedelta(seconds=60)
TOP_TABLES = 8


def system_status(db: Session, tenant_id: uuid.UUID, *, code_revision: str | None, otel_enabled: bool) -> SystemStatus:
    started = time.perf_counter()
    db_revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    latency_ms = round((time.perf_counter() - started) * 1000)
    now = utcnow()

    heartbeat = db.get(WorkerHeartbeat, WORKER_NAME)
    jobs = dict(
        db.execute(
            select(IntegrationJob.status, func.count())
            .where(IntegrationJob.tenant_id == tenant_id, IntegrationJob.status.in_([JOB_PENDING, JOB_RUNNING, JOB_FAILED]))
            .group_by(IntegrationJob.status)
        ).all()
    )
    oldest_pending = db.scalar(
        select(func.min(IntegrationJob.created_at)).where(
            IntegrationJob.tenant_id == tenant_id, IntegrationJob.status == JOB_PENDING
        )
    )
    audit_24h = db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.tenant_id == tenant_id, AuditLog.occurred_at >= now - timedelta(hours=24)
        )
    )
    size_mb, rcsi, tables = _database_details(db)

    return SystemStatus(
        version=settings.app_version,
        code_revision=code_revision,
        db_revision=db_revision,
        server_time=now,
        database=DatabaseStatus(latency_ms=latency_ms, size_mb=size_mb, read_committed_snapshot=rcsi),
        worker=WorkerStatus(
            last_seen=heartbeat.last_seen if heartbeat else None,
            healthy=heartbeat is not None and now - heartbeat.last_seen < WORKER_STALE_AFTER,
        ),
        integration=IntegrationQueueStatus(
            pending=jobs.get(JOB_PENDING, 0),
            running=jobs.get(JOB_RUNNING, 0),
            failed=jobs.get(JOB_FAILED, 0),
            oldest_pending_at=oldest_pending,
        ),
        audit_entries_24h=audit_24h or 0,
        tables=tables,
        telemetry=TelemetryStatus(
            otel_enabled=otel_enabled, log_format=settings.log_format, slow_request_ms=settings.slow_request_ms
        ),
    )


def _database_details(db: Session) -> tuple[float | None, bool | None, list[TableSize]]:
    """Size, RCSI and the largest tables. These catalog views need VIEW DATABASE STATE, which a customer-managed
    SQL Server login may not have: then they are simply left out. A savepoint keeps a refusal from aborting the request."""
    try:
        with db.begin_nested():
            size_mb = db.execute(
                text("SELECT CAST(SUM(CAST(size AS bigint)) * 8 / 1024.0 AS float) FROM sys.database_files")
            ).scalar()
            rcsi = db.execute(
                text("SELECT is_read_committed_snapshot_on FROM sys.databases WHERE database_id = DB_ID()")
            ).scalar()
            rows = db.execute(
                text(
                    f"SELECT TOP {TOP_TABLES} t.name, SUM(p.row_count) AS row_count "
                    "FROM sys.dm_db_partition_stats p JOIN sys.tables t ON t.object_id = p.object_id "
                    "WHERE p.index_id IN (0, 1) GROUP BY t.name ORDER BY row_count DESC"
                )
            ).all()
    except DBAPIError:
        return None, None, []
    return (
        round(size_mb, 1) if size_mb is not None else None,
        bool(rcsi) if rcsi is not None else None,
        [TableSize(name=name, rows=count) for name, count in rows],
    )
