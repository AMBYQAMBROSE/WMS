"""Supplier payables: posted goods receipts with a due date (posting date + the supplier's credit terms), and marking them
settled. The WMS does not record invoices or payments; accounts mark a receipt settled when its supplier has been paid."""

import uuid
from datetime import UTC, date

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader, DocumentLine
from app.services.document_common import DOC_GRN, get_document
from app.services.report_service import _num, _tz, today_local

GRN_POSTED = "POSTED"
STATUSES = ("open", "overdue", "settled")


class PayableService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID | None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, status: str | None = None, partner_id: uuid.UUID | None = None, limit: int = 500) -> dict:
        today = today_local()
        H, line, P = DocumentHeader, DocumentLine, BusinessPartner
        values = (
            select(line.document_id, func.sum(line.qty_actual * line.unit_price).label("value"))
            .where(line.tenant_id == self.tenant_id, line.unit_price.is_not(None))
            .group_by(line.document_id)
            .subquery()
        )
        conditions = [
            H.tenant_id == self.tenant_id, H.doc_type == DOC_GRN, H.status == GRN_POSTED,
            H.payment_due_date.is_not(None), H.partner_id.is_not(None),
        ]
        if partner_id:
            conditions.append(H.partner_id == partner_id)
        if status == "settled":
            conditions.append(H.settled_on.is_not(None))
        elif status == "overdue":
            conditions += [H.settled_on.is_(None), H.payment_due_date < today]
        elif status == "open":
            conditions.append(H.settled_on.is_(None))
        value = func.coalesce(values.c.value, 0)
        open_ = H.settled_on.is_(None)
        totals = self.db.execute(
            select(
                func.count(),
                func.sum(case((open_, value), else_=0)),
                func.sum(case((and_(open_, H.payment_due_date < today), value), else_=0)),
            )
            .select_from(H)
            .outerjoin(values, values.c.document_id == H.id)
            .where(*conditions)
        ).one()
        rows = self.db.execute(
            select(H.id, H.doc_no, H.posted_at, H.payment_due_date, H.settled_on, value.label("value"),
                   P.id.label("partner_id"), P.code, P.name, P.credit_terms_days)
            .select_from(H)
            .join(P, P.id == H.partner_id)
            .outerjoin(values, values.c.document_id == H.id)
            .where(*conditions)
            # Open ones by due date (most urgent first), settled ones most recent first
            .order_by(case((open_, 0), else_=1), case((open_, H.payment_due_date), else_=None), H.settled_on.desc(), H.doc_no)
            .limit(limit)
        ).mappings().all()
        return {
            "total": totals[0],
            "outstanding": _num(totals[1]),
            "overdue": _num(totals[2]),
            "rows": [
                {
                    "id": r["id"], "doc_no": r["doc_no"], "posted_at": r["posted_at"],
                    "partner": {"id": r["partner_id"], "code": r["code"], "name": r["name"]},
                    "credit_terms_days": r["credit_terms_days"],
                    "payment_due_date": r["payment_due_date"], "settled_on": r["settled_on"], "value": _num(r["value"]),
                    "days_overdue": ((r["settled_on"] or today) - r["payment_due_date"]).days,
                    "status": "settled" if r["settled_on"] else ("overdue" if r["payment_due_date"] < today else "open"),
                }
                for r in rows
            ],
        }

    def _receipt(self, grn_id: uuid.UUID) -> DocumentHeader:
        grn = get_document(self.db, self.tenant_id, DOC_GRN, grn_id, lock=True)
        if grn.status != GRN_POSTED or grn.payment_due_date is None:
            raise DomainError(f"Goods receipt {grn.doc_no} has no payable: only receipts posted since payables were introduced have one")
        return grn

    def settle(self, grn_id: uuid.UUID, settled_on: date) -> DocumentHeader:
        grn = self._receipt(grn_id)
        if settled_on > today_local():
            raise DomainError("The settlement date cannot be in the future")
        posted_day = grn.posted_at.replace(tzinfo=UTC).astimezone(_tz()).date() if grn.posted_at else None
        if posted_day and settled_on < posted_day:
            raise DomainError(f"The settlement date cannot be before the receipt was posted ({posted_day})")
        grn.settled_on = settled_on
        grn.updated_by = self.user_id
        self.db.flush()
        return grn

    def reopen(self, grn_id: uuid.UUID) -> DocumentHeader:
        grn = self._receipt(grn_id)
        if grn.settled_on is None:
            raise DomainError(f"Goods receipt {grn.doc_no} is not settled")
        grn.settled_on = None
        grn.updated_by = self.user_id
        self.db.flush()
        return grn
