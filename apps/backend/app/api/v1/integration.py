import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.core.event_catalog import EVENT_NAMES, EVENTS
from app.schemas.integration import (
    ConnectorIn,
    ConnectorRead,
    ConnectorUpdate,
    ConnectorWithSecret,
    EventTypeRead,
    IntegrationSummary,
    JobDetail,
    JobRead,
)
from app.services.integration_service import ConnectorService

router = APIRouter(route_class=TransactionalRoute, prefix="/integration", tags=["integration"])


def _service(db: Session, user: CurrentUser) -> ConnectorService:
    return ConnectorService(db, user.tenant_id, user.id)


@router.get("/event-types", response_model=list[EventTypeRead])
def list_event_types(_: CurrentUser = Depends(require_permission("integration.read"))):
    return [EventTypeRead(code=code, doc_type=doc_type, name=name) for code, doc_type, _, name in EVENTS]


@router.get("/summary", response_model=IntegrationSummary)
def summary(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.read")),
):
    return _service(db, user).summary()


@router.get("/connectors", response_model=list[ConnectorRead])
def list_connectors(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.read")),
):
    return [ConnectorRead.build(c) for c in _service(db, user).list()]


@router.post("/connectors", response_model=ConnectorWithSecret, status_code=status.HTTP_201_CREATED)
def create_connector(
    data: ConnectorIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    return ConnectorWithSecret.build(_service(db, user).create(data))


@router.put("/connectors/{connector_id}", response_model=ConnectorRead)
def update_connector(
    connector_id: uuid.UUID,
    data: ConnectorUpdate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    return ConnectorRead.build(_service(db, user).update(connector_id, data))


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    _service(db, user).delete(connector_id)


@router.post("/connectors/{connector_id}/rotate-secret", response_model=ConnectorWithSecret)
def rotate_secret(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    return ConnectorWithSecret.build(_service(db, user).rotate_secret(connector_id))


@router.post("/connectors/{connector_id}/test", response_model=JobRead)
def send_test(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    return JobRead.build(_service(db, user).send_test(connector_id), EVENT_NAMES)


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    connector_id: uuid.UUID | None = None,
    event_type: str | None = None,
    doc_no: str | None = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.read")),
):
    jobs = _service(db, user).jobs(status_filter, connector_id, event_type, doc_no, limit)
    return [JobRead.build(j, EVENT_NAMES) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.read")),
):
    job = _service(db, user).job(job_id)
    return JobDetail(**JobRead.build(job, EVENT_NAMES).model_dump(), payload=job.event.payload, logs=job.logs)


@router.post("/jobs/{job_id}/retry", response_model=JobRead)
def retry_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("integration.manage")),
):
    return JobRead.build(_service(db, user).retry(job_id), EVENT_NAMES)
