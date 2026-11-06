import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.versioning import ExpectedVersion


class ConnectorIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    endpoint_url: str = Field(min_length=1, max_length=500)
    event_types: list[str] = Field(default_factory=list)
    extra_headers: dict[str, str] | None = None
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    max_attempts: int = Field(default=8, ge=1, le=20)
    is_active: bool = True


class ConnectorUpdate(ConnectorIn, ExpectedVersion):
    code: str | None = None  # the code cannot change after creation; ignored on update


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    connector_type: str
    endpoint_url: str
    event_types: list[str]
    extra_headers: dict[str, str]
    timeout_seconds: int
    max_attempts: int
    is_active: bool
    row_version: int
    # Lists show only the last 4 characters; the full secret is returned only on create and regenerate
    secret_hint: str

    @field_validator("event_types", "extra_headers", mode="before")
    @classmethod
    def _parse_json(cls, value):
        return json.loads(value) if isinstance(value, str) else value

    @classmethod
    def build(cls, connector) -> "ConnectorRead":
        data = {c: getattr(connector, c) for c in cls.model_fields if c != "secret_hint"}
        return cls(**data, secret_hint="••••" + connector.secret[-4:])


class ConnectorWithSecret(ConnectorRead):
    secret: str

    @classmethod
    def build(cls, connector) -> "ConnectorWithSecret":
        base = ConnectorRead.build(connector)
        return cls(**base.model_dump(), secret=connector.secret)


class IntegrationLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_no: int
    requested_at: datetime
    duration_ms: int
    status_code: int | None
    success: bool
    error: str | None
    response_body: str | None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    attempts: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
    completed_at: datetime | None
    created_at: datetime
    event_type: str
    event_name: str
    doc_type: str | None
    doc_no: str | None
    document_id: uuid.UUID | None
    connector_id: uuid.UUID
    connector_name: str

    @classmethod
    def build(cls, job, event_names: dict[str, str]) -> "JobRead":
        return cls(
            **{f: getattr(job, f) for f in ("id", "status", "attempts", "next_attempt_at", "last_status_code",
                                             "last_error", "completed_at", "created_at", "connector_id")},
            event_type=job.event.event_type,
            event_name=event_names.get(job.event.event_type, job.event.event_type),
            doc_type=job.event.doc_type,
            doc_no=job.event.doc_no,
            document_id=job.event.document_id,
            connector_name=job.connector.name,
        )


class JobDetail(JobRead):
    payload: str | None
    logs: list[IntegrationLogRead]


class EventTypeRead(BaseModel):
    code: str
    doc_type: str
    name: str


class IntegrationSummary(BaseModel):
    jobs: dict[str, int]
    worker_last_seen: datetime | None
