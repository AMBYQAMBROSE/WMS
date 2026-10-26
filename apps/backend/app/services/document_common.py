import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.business_partner import BusinessPartner
from app.models.document import DocNumberRule, DocumentHeader
from app.models.item import Item, Uom
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.models.tenant import Tenant, TenantFeatureFlag

DOC_PO = "PO"
DOC_GRN = "GRN"
DOC_PUTAWAY = "PUTAWAY"

DEFAULT_PATTERN = "{PREFIX}{YYYY}{MM}{DD}-{SEQ:4}"
DEFAULT_PREFIXES = {DOC_PO: "PO", DOC_GRN: "GRN", DOC_PUTAWAY: "PA"}

FEATURE_ALLOW_OVER_RECEIPT = "ALLOW_OVER_RECEIPT"

_SEQ_TOKEN = re.compile(r"\{SEQ:(\d+)\}")
_DATE_TOKENS = (("{YYYY}", "%Y"), ("{MM}", "%m"), ("{DD}", "%d"))

# SQL Server 行锁提示：读取的同时加更新锁，直到事务结束，防止并发过账
LOCK_ROW = "WITH (UPDLOCK, ROWLOCK)"
LOCK_RANGE = "WITH (UPDLOCK, HOLDLOCK)"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def tenant_now(db: Session, tenant_id: uuid.UUID) -> datetime:
    tenant = db.get(Tenant, tenant_id)
    tz = ZoneInfo(tenant.default_timezone if tenant else "UTC")
    return datetime.now(tz)


def next_doc_no(db: Session, tenant_id: uuid.UUID, doc_type: str) -> str:
    rule = db.scalars(
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
        db.add(rule)

    now = tenant_now(db, tenant_id)
    period = "".join(now.strftime(fmt) for token, fmt in _DATE_TOKENS if token in rule.pattern)
    if rule.current_period != period:
        rule.current_period = period
        rule.current_seq = 0
    rule.current_seq += 1
    db.flush()

    doc_no = rule.pattern.replace("{PREFIX}", rule.prefix)
    for token, fmt in _DATE_TOKENS:
        doc_no = doc_no.replace(token, now.strftime(fmt))
    return _SEQ_TOKEN.sub(lambda m: str(rule.current_seq).zfill(int(m.group(1))), doc_no)


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
        # 所有对单据(含明细)的修改都先锁表头，明细不单独加锁
        stmt = stmt.with_hint(DocumentHeader, LOCK_ROW, "mssql").execution_options(
            populate_existing=True
        )
    document = db.scalars(stmt).unique().first()
    if document is None:
        raise NotFoundError("单据不存在")
    return document


def list_documents(
    db: Session,
    tenant_id: uuid.UUID,
    doc_type: str,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
    ref_document_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[DocumentHeader]:
    stmt = select(DocumentHeader).where(
        DocumentHeader.tenant_id == tenant_id,
        DocumentHeader.doc_type == doc_type,
        DocumentHeader.is_deleted == false(),
    )
    if status:
        stmt = stmt.where(DocumentHeader.status == status)
    if partner_id:
        stmt = stmt.where(DocumentHeader.partner_id == partner_id)
    if ref_document_id:
        stmt = stmt.where(DocumentHeader.ref_document_id == ref_document_id)
    stmt = stmt.order_by(DocumentHeader.created_at.desc(), DocumentHeader.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).unique())


def require_status(document: DocumentHeader, allowed: tuple[str, ...], action: str) -> None:
    if document.status not in allowed:
        raise ConflictError(f"单据 {document.doc_no} 当前状态为 {document.status}，不能{action}")


def get_supplier(db: Session, tenant_id: uuid.UUID, partner_id: uuid.UUID) -> BusinessPartner:
    partner = db.get(BusinessPartner, partner_id)
    if partner is None or partner.tenant_id != tenant_id or partner.is_deleted:
        raise DomainError("供应商不存在")
    if not partner.is_active:
        raise DomainError(f"供应商 {partner.code} 已停用")
    if partner.partner_type not in ("supplier", "both"):
        raise DomainError(f"{partner.code} 不是供应商")
    return partner


def get_active_item(db: Session, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.tenant_id != tenant_id or item.is_deleted:
        raise DomainError("商品不存在")
    if not item.is_active:
        raise DomainError(f"商品 {item.sku_code} 已停用")
    return item


def get_uom(db: Session, tenant_id: uuid.UUID, uom_id: uuid.UUID) -> Uom:
    uom = db.get(Uom, uom_id)
    if uom is None or uom.tenant_id != tenant_id or uom.is_deleted:
        raise DomainError("计量单位不存在")
    return uom


def get_stock_location(
    db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID, allowed_types=STOCK_LOCATION_TYPES
) -> Location:
    location = db.get(Location, location_id)
    if location is None or location.tenant_id != tenant_id or location.is_deleted:
        raise DomainError("仓位不存在")
    if not location.is_active:
        raise DomainError(f"仓位 {location.code} 已停用")
    if location.is_locked:
        raise DomainError(f"仓位 {location.code} 已锁定")
    if location.location_type not in allowed_types:
        raise DomainError(
            f"仓位 {location.code} 类型为 {location.location_type}，此处只允许 {'/'.join(allowed_types)}"
        )
    return location


def normalize_tracking(item: Item, batch_no: str | None, expiry_date):
    """按商品的批次/效期管理开关校验并规整：未启用管理的商品忽略传入值，避免产生多余的库存维度。"""
    batch_no = (batch_no or "").strip() or None
    if item.is_batch_managed:
        if batch_no is None:
            raise DomainError(f"商品 {item.sku_code} 启用了批次管理，必须填写批次号")
    else:
        batch_no = None
    if item.is_expiry_managed:
        if expiry_date is None:
            raise DomainError(f"商品 {item.sku_code} 启用了效期管理，必须填写到期日")
    else:
        expiry_date = None
    return batch_no, expiry_date
