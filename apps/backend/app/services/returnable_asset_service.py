import uuid
from decimal import Decimal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.formatting import qty_text
from app.models.business_partner import BusinessPartner
from app.models.returnable_asset import ReturnableAssetTxn, ReturnableAssetType
from app.schemas.document import PartnerBrief
from app.schemas.extension import AssetBalanceRow, AssetTxnIn, AssetTypeIn, AssetTypeRead
from app.services.document_common import LOCK_ROW, utcnow

ZERO = Decimal(0)


class ReturnableAssetService:
    """Returnable asset ledger (Ninso Tool / ToolOneMany / ToolReturn):
    issues (ISSUE) to a partner are positive, returns (RETURN) negative; outstanding = ledger total. A return cannot exceed what is outstanding.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list_types(self) -> list[ReturnableAssetType]:
        return list(
            self.db.scalars(
                select(ReturnableAssetType)
                .where(ReturnableAssetType.tenant_id == self.tenant_id, ReturnableAssetType.is_deleted == false())
                .order_by(ReturnableAssetType.code)
            )
        )

    def create_type(self, data: AssetTypeIn) -> ReturnableAssetType:
        asset_type = ReturnableAssetType(
            tenant_id=self.tenant_id, created_by=self.user_id, updated_by=self.user_id, **data.model_dump()
        )
        self.db.add(asset_type)
        self.db.flush()
        return asset_type

    def list_txns(
        self, partner_id: uuid.UUID | None = None, asset_type_id: uuid.UUID | None = None, limit: int = 200
    ) -> list[ReturnableAssetTxn]:
        stmt = select(ReturnableAssetTxn).where(ReturnableAssetTxn.tenant_id == self.tenant_id)
        if partner_id:
            stmt = stmt.where(ReturnableAssetTxn.partner_id == partner_id)
        if asset_type_id:
            stmt = stmt.where(ReturnableAssetTxn.asset_type_id == asset_type_id)
        stmt = stmt.order_by(ReturnableAssetTxn.occurred_at.desc(), ReturnableAssetTxn.id).limit(limit)
        return list(self.db.scalars(stmt).unique())

    def record(self, data: AssetTxnIn) -> ReturnableAssetTxn:
        # Lock the partner row: returns for the same partner queue up, so concurrent returns cannot push outstanding below zero
        partner = self.db.scalars(
            select(BusinessPartner)
            .with_hint(BusinessPartner, LOCK_ROW, "mssql")
            .where(BusinessPartner.id == data.partner_id, BusinessPartner.tenant_id == self.tenant_id)
        ).first()
        if partner is None or partner.is_deleted:
            raise DomainError("Business partner not found")
        asset_type = self.db.get(ReturnableAssetType, data.asset_type_id)
        if asset_type is None or asset_type.tenant_id != self.tenant_id or asset_type.is_deleted:
            raise NotFoundError("Returnable asset type not found")
        if not asset_type.is_active:
            raise DomainError(f"Returnable asset {asset_type.code} is inactive")

        if data.txn_type == "RETURN":
            outstanding = self._outstanding(partner.id, asset_type.id)
            if data.qty > outstanding:
                raise DomainError(
                    f"{partner.name} has {qty_text(outstanding)} {asset_type.name} outstanding; cannot return {qty_text(data.qty)}"
                )
        txn = ReturnableAssetTxn(
            tenant_id=self.tenant_id,
            partner_id=partner.id,
            asset_type_id=asset_type.id,
            txn_type=data.txn_type,
            qty_change=data.qty if data.txn_type == "ISSUE" else -data.qty,
            ref_document_id=data.ref_document_id,
            remark=data.remark,
            occurred_at=utcnow(),
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.db.add(txn)
        self.db.flush()
        return txn

    def balances(self, partner_id: uuid.UUID | None = None) -> list[AssetBalanceRow]:
        stmt = (
            select(
                ReturnableAssetTxn.partner_id,
                ReturnableAssetTxn.asset_type_id,
                func.sum(ReturnableAssetTxn.qty_change),
            )
            .where(ReturnableAssetTxn.tenant_id == self.tenant_id)
            .group_by(ReturnableAssetTxn.partner_id, ReturnableAssetTxn.asset_type_id)
            .having(func.sum(ReturnableAssetTxn.qty_change) != 0)
        )
        if partner_id:
            stmt = stmt.where(ReturnableAssetTxn.partner_id == partner_id)
        rows = []
        for p_id, t_id, qty in self.db.execute(stmt):
            rows.append(
                AssetBalanceRow(
                    partner=PartnerBrief.model_validate(self.db.get(BusinessPartner, p_id)),
                    asset_type=AssetTypeRead.model_validate(self.db.get(ReturnableAssetType, t_id)),
                    outstanding=qty,
                )
            )
        return sorted(rows, key=lambda r: (r.partner.code, r.asset_type.code))

    def _outstanding(self, partner_id: uuid.UUID, asset_type_id: uuid.UUID) -> Decimal:
        total = self.db.scalar(
            select(func.sum(ReturnableAssetTxn.qty_change)).where(
                ReturnableAssetTxn.tenant_id == self.tenant_id,
                ReturnableAssetTxn.partner_id == partner_id,
                ReturnableAssetTxn.asset_type_id == asset_type_id,
            )
        )
        return total or ZERO
