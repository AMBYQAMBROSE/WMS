import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.db import numbering_engine
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.business_partner import BusinessPartner
from app.models.document import DocNumberRule, DocumentHeader, DocumentLocation
from app.models.item import Item, Uom
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.models.reason_code import ReasonCode
from app.models.tenant import Tenant, TenantFeatureFlag

DOC_PO = "PO"
DOC_GRN = "GRN"
DOC_PUTAWAY = "PUTAWAY"
DOC_ADJUST = "ADJUST"
DOC_MOVE = "MOVE"
DOC_COUNT = "COUNT"
DOC_SO = "SO"
DOC_PICK = "PICK"
DOC_SHIP = "SHIP"
DOC_RETURN_IN = "RETURN_IN"
DOC_RETURN_OUT = "RETURN_OUT"
DOC_REPACK = "REPACK"

# Status of a cycle count in progress: locations covered by such a count are frozen for stock movements
COUNT_IN_PROGRESS = "COUNTING"

DEFAULT_PATTERN = "{PREFIX}{YYYY}{MM}{DD}-{SEQ:4}"
DEFAULT_PREFIXES = {
    DOC_PO: "PO",
    DOC_GRN: "GRN",
    DOC_PUTAWAY: "PA",
    DOC_ADJUST: "ADJ",
    DOC_MOVE: "MV",
    DOC_COUNT: "CC",
    DOC_SO: "SO",
    DOC_PICK: "PK",
    DOC_SHIP: "DO",
    DOC_RETURN_IN: "RI",
    DOC_RETURN_OUT: "RO",
    DOC_REPACK: "RP",
}

from app.core.feature_catalog import FEATURE_ALLOW_OVER_RECEIPT  # noqa: E402,F401  still exported from here

_SEQ_TOKEN = re.compile(r"\{SEQ:(\d+)\}")
_DATE_TOKENS = (("{YYYY}", "%Y"), ("{MM}", "%m"), ("{DD}", "%d"))

# SQL Server row lock hint: take an update lock while reading, held until the transaction ends, to prevent concurrent posting
LOCK_ROW = "WITH (UPDLOCK, ROWLOCK)"
LOCK_RANGE = "WITH (UPDLOCK, HOLDLOCK)"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def tenant_now(db: Session, tenant_id: uuid.UUID) -> datetime:
    tenant = db.get(Tenant, tenant_id)
    tz = ZoneInfo(tenant.default_timezone if tenant else "UTC")
    return datetime.now(tz)


def next_doc_no(db: Session, tenant_id: uuid.UUID, doc_type: str) -> str:
    """Take the next document number. It is taken in a separate short transaction and committed at once: inside the business
    transaction the numbering row would stay locked until that transaction ends, so documents of one type could only be created one at a time (p95 of 7 s in load tests).
    Trade-off: if the business transaction rolls back the number is lost, so numbers can have gaps (as in most ERPs)."""
    with Session(bind=numbering_engine, autoflush=False) as numbering:
        rule = numbering.scalars(
            select(DocNumberRule)
            .with_hint(DocNumberRule, LOCK_RANGE, "mssql")
            .where(DocNumberRule.tenant_id == tenant_id, DocNumberRule.doc_type == doc_type)
        ).first()
        if rule is None:
            rule = DocNumberRule(
                tenant_id=tenant_id,
                doc_type=doc_type,
                prefix=DEFAULT_PREFIXES.get(doc_type, doc_type),
                pattern=DEFAULT_PATTERN,
            )
            numbering.add(rule)

        now = tenant_now(numbering, tenant_id)
        period = "".join(now.strftime(fmt) for token, fmt in _DATE_TOKENS if token in rule.pattern)
        if rule.current_period != period:
            rule.current_period = period
            rule.current_seq = 0
        rule.current_seq += 1
        seq, pattern, prefix = rule.current_seq, rule.pattern, rule.prefix
        numbering.commit()

    doc_no = pattern.replace("{PREFIX}", prefix)
    for token, fmt in _DATE_TOKENS:
        doc_no = doc_no.replace(token, now.strftime(fmt))
    return _SEQ_TOKEN.sub(lambda m: str(seq).zfill(int(m.group(1))), doc_no)


def is_feature_enabled(db: Session, tenant_id: uuid.UUID, feature_code: str) -> bool:
    flag = db.scalars(
        select(TenantFeatureFlag).where(
            TenantFeatureFlag.tenant_id == tenant_id,
            TenantFeatureFlag.feature_code == feature_code,
            TenantFeatureFlag.is_deleted == false(),
        )
    ).first()
    return bool(flag and flag.is_enabled)


def get_document(
    db: Session, tenant_id: uuid.UUID, doc_type: str, document_id: uuid.UUID, lock: bool = False
) -> DocumentHeader:
    stmt = select(DocumentHeader).where(
        DocumentHeader.tenant_id == tenant_id,
        DocumentHeader.doc_type == doc_type,
        DocumentHeader.id == document_id,
        DocumentHeader.is_deleted == false(),
    )
    if lock:
        # Every change to a document (including lines) locks the header first; lines are not locked separately
        stmt = stmt.with_hint(DocumentHeader, LOCK_ROW, "mssql").execution_options(
            populate_existing=True
        )
    document = db.scalars(stmt).unique().first()
    if document is None:
        raise NotFoundError("Document not found")
    return document


def find_by_client_request(
    db: Session, tenant_id: uuid.UUID, doc_type: str, client_request_id: str | None
) -> DocumentHeader | None:
    """Idempotent submit: if a document already exists for this request ID, return it. If another document type uses the ID, the client has a bug: report a conflict."""
    if not client_request_id:
        return None
    document = db.scalars(
        select(DocumentHeader).where(
            DocumentHeader.tenant_id == tenant_id,
            DocumentHeader.client_request_id == client_request_id,
        )
    ).unique().first()
    if document is not None and document.doc_type != doc_type:
        raise ConflictError(f"Request ID already used by document {document.doc_no}")
    return document


def list_documents(
    db: Session,
    tenant_id: uuid.UUID,
    doc_type: str,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
    ref_document_id: uuid.UUID | None = None,
    doc_no: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[DocumentHeader]:
    stmt = select(DocumentHeader).where(
        DocumentHeader.tenant_id == tenant_id,
        DocumentHeader.doc_type == doc_type,
        DocumentHeader.is_deleted == false(),
    )
    if doc_no:
        stmt = stmt.where(DocumentHeader.doc_no == doc_no.strip())
    if status:
        stmt = stmt.where(DocumentHeader.status == status)
    if partner_id:
        stmt = stmt.where(DocumentHeader.partner_id == partner_id)
    if ref_document_id:
        stmt = stmt.where(DocumentHeader.ref_document_id == ref_document_id)
    # Both columns descending so the index (tenant_id, doc_type, created_at[, id]) can be read backwards without sorting the whole document type
    stmt = stmt.order_by(DocumentHeader.created_at.desc(), DocumentHeader.id.desc()).offset(skip).limit(limit)
    return list(db.scalars(stmt).unique())


def require_status(document: DocumentHeader, allowed: tuple[str, ...], action: str) -> None:
    if document.status not in allowed:
        raise ConflictError(f"Document {document.doc_no} is {document.status}; cannot {action}")


def get_supplier(db: Session, tenant_id: uuid.UUID, partner_id: uuid.UUID) -> BusinessPartner:
    partner = db.get(BusinessPartner, partner_id)
    if partner is None or partner.tenant_id != tenant_id or partner.is_deleted:
        raise DomainError("Supplier not found")
    if not partner.is_active:
        raise DomainError(f"Supplier {partner.code} is inactive")
    if partner.partner_type not in ("supplier", "both"):
        raise DomainError(f"{partner.code} is not a supplier")
    return partner


def get_reason(db: Session, tenant_id: uuid.UUID, reason_code_id: uuid.UUID | None, category: str, label: str) -> ReasonCode:
    reason = db.get(ReasonCode, reason_code_id) if reason_code_id else None
    if reason is None or reason.tenant_id != tenant_id or reason.is_deleted or reason.category != category:
        raise DomainError(f"{label} not found")
    if not reason.is_active:
        raise DomainError(f"{label} {reason.code} is inactive")
    return reason


def get_customer(db: Session, tenant_id: uuid.UUID, partner_id: uuid.UUID) -> BusinessPartner:
    partner = db.get(BusinessPartner, partner_id)
    if partner is None or partner.tenant_id != tenant_id or partner.is_deleted:
        raise DomainError("Customer not found")
    if not partner.is_active:
        raise DomainError(f"Customer {partner.code} is inactive")
    if partner.partner_type not in ("customer", "both"):
        raise DomainError(f"{partner.code} is not a customer")
    return partner


def get_active_item(db: Session, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.tenant_id != tenant_id or item.is_deleted:
        raise DomainError("Item not found")
    if not item.is_active:
        raise DomainError(f"Item {item.sku_code} is inactive")
    return item


def get_uom(db: Session, tenant_id: uuid.UUID, uom_id: uuid.UUID) -> Uom:
    uom = db.get(Uom, uom_id)
    if uom is None or uom.tenant_id != tenant_id or uom.is_deleted:
        raise DomainError("Unit of measure not found")
    return uom


def get_stock_location(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID, allowed_types=STOCK_LOCATION_TYPES
) -> Location:
    location = db.get(Location, location_id)
    if location is None or location.tenant_id != tenant_id or location.is_deleted:
        raise DomainError("Location not found")
    if not location.is_active:
        raise DomainError(f"Location {location.code} is inactive")
    if location.is_locked:
        raise DomainError(f"Location {location.code} is locked")
    if location.location_type not in allowed_types:
        raise DomainError(
            f"Location {location.code} is of type {location.location_type}; only {'/'.join(allowed_types)} allowed here"
        )
    counting = active_count_for_location(db, tenant_id, location.id)
    if counting is not None:
        raise DomainError(f"Location {location.code} is being counted ({counting.doc_no}); stock movements are paused")
    return location


def active_count_for_location(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID
) -> DocumentHeader | None:
    return db.scalars(
        select(DocumentHeader)
        .join(DocumentLocation, DocumentLocation.document_id == DocumentHeader.id)
        .where(
            DocumentHeader.tenant_id == tenant_id,
            DocumentHeader.doc_type == DOC_COUNT,
            DocumentHeader.status == COUNT_IN_PROGRESS,
            DocumentHeader.is_deleted == false(),
            DocumentLocation.location_id == location_id,
        )
    ).unique().first()


def normalize_tracking(item: Item, batch_no: str | None, expiry_date):
    """Validate and normalize per the item's batch/expiry settings: values for items without those settings are ignored to avoid extra stock dimensions."""
    batch_no = (batch_no or "").strip() or None
    if item.is_batch_managed:
        if batch_no is None:
            raise DomainError(f"Item {item.sku_code} is batch managed; a batch number is required")
    else:
        batch_no = None
    if item.is_expiry_managed:
        if expiry_date is None:
            raise DomainError(f"Item {item.sku_code} is expiry managed; an expiry date is required")
    else:
        expiry_date = None
    return batch_no, expiry_date
