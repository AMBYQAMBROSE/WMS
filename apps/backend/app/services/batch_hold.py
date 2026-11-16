"""Batches held by an active recall (RECALL documents, app/services/recall_service.py).

A held batch is never allocated to an order, and a shipment carrying it cannot be posted. Stock already allocated or
picked stays where it is, so the warehouse can return it to stock and quarantine it. Kept apart from the recall
service so the stock and shipment services can use it without importing the services a recall itself uses.
"""

import uuid

from sqlalchemy import exists, false, select
from sqlalchemy.orm import Session

from app.models.document import DocumentHeader, DocumentLine
from app.services.document_common import DOC_RECALL

RECALL_ACTIVE = "ACTIVE"
RECALL_RELEASED = "RELEASED"


def _active(tenant_id: uuid.UUID):
    return (
        DocumentHeader.tenant_id == tenant_id,
        DocumentHeader.doc_type == DOC_RECALL,
        DocumentHeader.status == RECALL_ACTIVE,
        DocumentHeader.is_deleted == false(),
    )


def held(tenant_id: uuid.UUID, item_col, batch_col):
    """SQL condition: the (item, batch) in these columns is under an active recall. Stock without a batch never is."""
    return exists(
        select(DocumentLine.id)
        .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
        .where(*_active(tenant_id), DocumentLine.item_id == item_col, DocumentLine.batch_no == batch_col)
    )


def active_recall(db: Session, tenant_id: uuid.UUID, item_id: uuid.UUID, batch_no: str | None) -> DocumentHeader | None:
    if not batch_no:
        return None
    return db.scalars(
        select(DocumentHeader)
        .join(DocumentLine, DocumentLine.document_id == DocumentHeader.id)
        .where(*_active(tenant_id), DocumentLine.item_id == item_id, DocumentLine.batch_no == batch_no)
    ).unique().first()


def active_recalls(db: Session, tenant_id: uuid.UUID) -> dict[tuple[uuid.UUID, str], DocumentHeader]:
    """Every held (item, batch) -> its recall; there are only ever a handful"""
    rows = db.execute(
        select(DocumentLine.item_id, DocumentLine.batch_no, DocumentHeader)
        .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
        .where(*_active(tenant_id))
    ).unique()
    return {(item_id, batch_no): doc for item_id, batch_no, doc in rows}
