from datetime import datetime

from pydantic import BaseModel


class DatabaseStatus(BaseModel):
    latency_ms: int
    # Null when the database login lacks VIEW DATABASE STATE (customer-managed SQL Server)
    size_mb: float | None
    read_committed_snapshot: bool | None


class WorkerStatus(BaseModel):
    last_seen: datetime | None
    healthy: bool


class IntegrationQueueStatus(BaseModel):
    pending: int
    running: int
    failed: int
    oldest_pending_at: datetime | None


class TableSize(BaseModel):
    name: str
    rows: int


class TelemetryStatus(BaseModel):
    otel_enabled: bool
    log_format: str
    slow_request_ms: int


class SystemStatus(BaseModel):
    version: str
    code_revision: str | None
    db_revision: str | None
    server_time: datetime
    database: DatabaseStatus
    worker: WorkerStatus
    integration: IntegrationQueueStatus
    audit_entries_24h: int
    # Largest tables by rows; empty without VIEW DATABASE STATE
    tables: list[TableSize]
    telemetry: TelemetryStatus
