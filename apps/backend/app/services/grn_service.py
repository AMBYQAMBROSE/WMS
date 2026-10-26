import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.schemas.document import GrnIn
from app.services.document_common import (
    DOC_GRN,
    DOC_PO,
    FEATURE_ALLOW_OVER_RECEIPT,
    get_document,
    get_stock_location,
    is_feature_enabled,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.purchase_order_service import (
    PO_PARTIALLY_RECEIVED,
    PO_RECEIVABLE,
    PO_RECEIVED,
)
from app.services.stock_service import MOVE_RECEIVE, Movement, apply_movements, to_base_qty

GRN_DRAFT = "DRAFT"
GRN_POSTED = "POSTED"
GRN_CANCELLED = "CANCELLED"


class GrnService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_GRN, **filters)

    def get(self, grn_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_GRN, grn_id, lock=lock)

    def create(self, data: GrnIn) -> DocumentHeader:
        po = get_document(self.db, self.tenant_id, DOC_PO, data.po_id)
        require_status(po, PO_RECEIVABLE, "收货")
        location = get_stock_location(self.db, self.tenant_id, data.location_id)
        po_lines = {line.id: line for line in po.lines}

        lines = []
        requested: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for line_no, line_in in enumerate(data.lines, start=1):
            po_line = po_lines.get(line_in.po_line_id)
            if po_line is None:
                raise DomainError(f"第 {line_no} 行不属于采购单 {po.doc_no}")
            batch_no, expiry_date = normalize_tracking(
                po_line.item, line_in.batch_no, line_in.expiry_date
            )
            requested[po_line.id] += line_in.qty
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=po_line.item_id,
                    uom_id=po_line.uom_id,
                    # 应收：建单时该采购行的未收数量，仅供参考
                    qty_planned=max(po_line.qty_planned - po_line.qty_actual, Decimal(0)),
                    qty_actual=line_in.qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    to_location_id=location.id,
                    ref_line_id=po_line.id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        self._check_over_receipt(po_lines, requested)

        grn = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_GRN,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_GRN),
            status=GRN_DRAFT,
            partner_id=po.partner_id,
            ref_document_id=po.id,
            location_id=location.id,
            remark=data.remark,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        grn.lines = lines
        self.db.add(grn)
        self.db.flush()
        return self.get(grn.id)

    def post(self, grn_id: uuid.UUID) -> DocumentHeader:
        # 加锁顺序固定为 GRN → PO，同一采购单的多张收货单并发过账会在 PO 锁上排队
        grn = self.get(grn_id, lock=True)
        require_status(grn, (GRN_DRAFT,), "过账")
        po = get_document(self.db, self.tenant_id, DOC_PO, grn.ref_document_id, lock=True)
        require_status(po, PO_RECEIVABLE, "收货")
        get_stock_location(self.db, self.tenant_id, grn.location_id)

        po_lines = {line.id: line for line in po.lines}
        requested: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        movements = []
        for line in grn.lines:
            # 建单后商品的批次/效期开关可能被改过，过账时再校验一次
            batch_no, expiry_date = normalize_tracking(line.item, line.batch_no, line.expiry_date)
            requested[line.ref_line_id] += line.qty_actual
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=grn.location_id,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    qty_change=to_base_qty(
                        self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual
                    ),
                    movement_type=MOVE_RECEIVE,
                    ref_line_id=line.id,
                )
            )
        self._check_over_receipt(po_lines, requested)

        for po_line_id, qty in requested.items():
            po_lines[po_line_id].qty_actual += qty
        fully_received = all(line.qty_actual >= line.qty_planned for line in po.lines)
        po.status = PO_RECEIVED if fully_received else PO_PARTIALLY_RECEIVED
        po.updated_by = self.user_id
        po.row_version += 1

        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        grn.status = GRN_POSTED
        grn.posted_at = utcnow()
        grn.updated_by = self.user_id
        grn.row_version += 1
        self.db.flush()
        return grn

    def cancel(self, grn_id: uuid.UUID) -> DocumentHeader:
        grn = self.get(grn_id, lock=True)
        require_status(grn, (GRN_DRAFT,), "取消")
        grn.status = GRN_CANCELLED
        grn.updated_by = self.user_id
        grn.row_version += 1
        self.db.flush()
        return grn

    def _check_over_receipt(
        self, po_lines: dict[uuid.UUID, DocumentLine], requested: dict[uuid.UUID, Decimal]
    ) -> None:
        if is_feature_enabled(self.db, self.tenant_id, FEATURE_ALLOW_OVER_RECEIPT):
            return
        for po_line_id, qty in requested.items():
            po_line = po_lines[po_line_id]
            if po_line.qty_actual + qty > po_line.qty_planned:
                raise DomainError(
                    f"商品 {po_line.item.sku_code} 超收：订购 {po_line.qty_planned.normalize()}，"
                    f"已收 {po_line.qty_actual.normalize()}，本次 {qty.normalize()}"
                )
