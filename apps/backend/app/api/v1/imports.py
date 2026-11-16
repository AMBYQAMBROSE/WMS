import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.api.routing import TransactionalRoute
from app.services.import_service import KINDS, ImportService, template

router = APIRouter(route_class=TransactionalRoute, prefix="/imports", tags=["imports"])

Kind = Literal["items", "locations", "partners", "opening_stock", "purchase_orders", "sales_orders"]
# Same as nginx client_max_body_size
MAX_FILE_BYTES = 20 * 1024 * 1024


class ImportErrorRow(BaseModel):
    row: int
    column: str
    message: str


class ImportedDocument(BaseModel):
    """An order from an order import; document_id/no are set once it is created (empty while only validating)"""

    ref: str | None
    partner: str
    lines: int
    document_id: uuid.UUID | None
    document_no: str | None


class ImportResultRead(BaseModel):
    kind: str
    total: int
    created: int
    updated: int
    error_count: int
    errors: list[ImportErrorRow]
    warnings: list[str]
    committed: bool
    document_id: uuid.UUID | None
    document_no: str | None
    documents: list[ImportedDocument] = []


class ImportKindRead(BaseModel):
    key: str
    name: str
    permissions: list[str]
    allowed: bool


def _check(user: CurrentUser, kind: Kind) -> None:
    missing = [p for p in KINDS[kind].permissions if p not in user.permissions]
    if missing:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {', '.join(missing)}")


@router.get("", response_model=list[ImportKindRead])
def list_kinds(user: CurrentUser = Depends(get_current_user)):
    return [
        ImportKindRead(key=k.key, name=k.name, permissions=list(k.permissions),
                       allowed=all(p in user.permissions for p in k.permissions))
        for k in KINDS.values()
    ]


@router.get("/{kind}/template")
def download_template(kind: Kind, user: CurrentUser = Depends(get_current_user)):
    _check(user, kind)
    filename = f"Import template - {KINDS[kind].name}.xlsx"
    return Response(
        content=template(kind),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{kind}", response_model=ImportResultRead)
def run_import(
    kind: Kind,
    file: UploadFile = File(...),
    commit: bool = Query(default=False, description="false validates only; true imports when validation passes"),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    _check(user, kind)
    # Sync endpoint (runs in the thread pool): imports do a lot of database work; as async it would block the whole process's event loop
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is larger than 20MB; split it")
    result = ImportService(db, user.tenant_id, user.id).run(kind, file.filename or "", content, commit)
    return ImportResultRead(**result.__dict__)
