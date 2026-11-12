"""Shopping cart: a quick way for people outside the warehouse office to order.

Customer accounts (User.partner_id set) always order for their own customer and only see that customer's orders.
Internal staff choose the customer per order and see the orders they placed. Either way the cart creates a DRAFT
sales order through SalesOrderService, so it is validated exactly like a hand-entered order and the warehouse confirms it.

The cart contents themselves live in the user's preferences (key "cart"), so they follow the user to any PC.
"""

import uuid
from decimal import Decimal

from sqlalchemy import false, func, or_, select, true
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import DomainError, ForbiddenError, NotFoundError
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader
from app.models.item import Item, ItemUomConversion, Uom
from app.models.location import Location
from app.models.stock import StockBalance
from app.schemas.cart import CartOrderIn, CartUom, CatalogItem, CatalogPage
from app.schemas.document import UomBrief
from app.schemas.outbound import SalesOrderIn, SalesOrderLineIn, SalesOrderRead
from app.services.document_common import DOC_SO, get_customer, tenant_now
from app.services.sales_order_service import SO_DRAFT, SalesOrderService

MAX_CATEGORIES = 200
MAX_CUSTOMERS = 50


class CartService:
    def __init__(self, db: Session, user: CurrentUser):
        self.db = db
        self.user = user
        self.tenant_id = user.tenant_id

    # ------------------------------------------------------------ catalog

    def _available(self):
        """Available stock per item (base units) in the bins allocation draws from: active, unlocked, not expired"""
        today = tenant_now(self.db, self.tenant_id).date()
        return (
            select(
                StockBalance.item_id.label("item_id"),
                func.sum(StockBalance.qty_on_hand - StockBalance.qty_allocated).label("available"),
            )
            .join(Location, Location.id == StockBalance.location_id)
            .where(
                StockBalance.tenant_id == self.tenant_id,
                Location.location_type == "BIN",
                Location.is_active == true(),
                Location.is_locked == false(),
                Location.is_deleted == false(),
                or_(StockBalance.expiry_date.is_(None), StockBalance.expiry_date >= today),
            )
            .group_by(StockBalance.item_id)
            .subquery()
        )

    def catalog(
        self, keyword: str | None, category: str | None, in_stock_only: bool, skip: int, limit: int
    ) -> CatalogPage:
        available = self._available()
        qty = func.coalesce(available.c.available, 0)
        stmt = (
            select(Item, qty)
            .outerjoin(available, available.c.item_id == Item.id)
            .where(Item.tenant_id == self.tenant_id, Item.is_deleted == false(), Item.is_active == true())
        )
        if keyword and keyword.strip():
            needle = keyword.strip()
            stmt = stmt.where(or_(
                Item.sku_code.contains(needle, autoescape=True),
                Item.name.contains(needle, autoescape=True),
                Item.barcode == needle,
            ))
        if category:
            stmt = stmt.where(Item.category == category)
        if in_stock_only:
            stmt = stmt.where(qty > 0)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.execute(stmt.order_by(Item.sku_code).offset(skip).limit(limit)).all()

        # Units each item can be ordered in: its base unit plus every unit with a conversion to it
        ids = [item.id for item, _ in rows]
        extra: dict[uuid.UUID, list[CartUom]] = {}
        if ids:
            for conv, uom in self.db.execute(
                select(ItemUomConversion, Uom)
                .join(Uom, Uom.id == ItemUomConversion.from_uom_id)
                .join(Item, Item.id == ItemUomConversion.item_id)
                .where(
                    ItemUomConversion.tenant_id == self.tenant_id,
                    ItemUomConversion.item_id.in_(ids),
                    ItemUomConversion.to_uom_id == Item.base_uom_id,
                    ItemUomConversion.is_deleted == false(),
                )
                .order_by(ItemUomConversion.factor)
            ):
                extra.setdefault(conv.item_id, []).append(
                    CartUom(id=uom.id, code=uom.code, name=uom.name, factor=conv.factor)
                )

        items = [
            CatalogItem(
                id=item.id,
                sku_code=item.sku_code,
                name=item.name,
                category=item.category,
                barcode=item.barcode,
                base_uom=UomBrief.model_validate(item.base_uom),
                uoms=[
                    CartUom(id=item.base_uom.id, code=item.base_uom.code, name=item.base_uom.name, factor=Decimal(1)),
                    *extra.get(item.id, []),
                ],
                available=max(Decimal(available_qty), Decimal(0)),
            )
            for item, available_qty in rows
        ]
        categories = list(self.db.scalars(
            select(Item.category)
            .where(Item.tenant_id == self.tenant_id, Item.is_deleted == false(), Item.is_active == true(),
                   Item.category.is_not(None))
            .distinct()
            .order_by(Item.category)
            .limit(MAX_CATEGORIES)
        ))
        return CatalogPage(items=items, total=total, categories=categories)

    # ------------------------------------------------------------ customers

    def customers(self, keyword: str | None) -> list[BusinessPartner]:
        """Customers the user may order for: a customer account gets only its own"""
        if self.user.partner_id:
            return [get_customer(self.db, self.tenant_id, self.user.partner_id)]
        stmt = select(BusinessPartner).where(
            BusinessPartner.tenant_id == self.tenant_id,
            BusinessPartner.is_deleted == false(),
            BusinessPartner.is_active == true(),
            BusinessPartner.partner_type.in_(("customer", "both")),
        )
        if keyword and keyword.strip():
            needle = keyword.strip()
            stmt = stmt.where(or_(
                BusinessPartner.code.contains(needle, autoescape=True),
                BusinessPartner.name.contains(needle, autoescape=True),
            ))
        return list(self.db.scalars(stmt.order_by(BusinessPartner.code).limit(MAX_CUSTOMERS)))

    # ------------------------------------------------------------ orders

    def submit(self, data: CartOrderIn) -> SalesOrderRead:
        partner_id = data.partner_id
        if self.user.partner_id:
            if partner_id and partner_id != self.user.partner_id:
                raise ForbiddenError("This account can only order for its own customer")
            partner_id = self.user.partner_id
        if partner_id is None:
            raise DomainError("Choose the customer to order for")
        # The same item in the same unit added twice becomes one line
        merged: dict[tuple[uuid.UUID, uuid.UUID], SalesOrderLineIn] = {}
        for line in data.lines:
            key = (line.item_id, line.uom_id)
            if key in merged:
                merged[key].qty += line.qty
            else:
                merged[key] = SalesOrderLineIn(item_id=line.item_id, uom_id=line.uom_id, qty=line.qty)
        service = SalesOrderService(self.db, self.tenant_id, self.user.id)
        so = service.create(SalesOrderIn(
            partner_id=partner_id, expected_date=data.expected_date, remark=data.remark, lines=list(merged.values()),
        ))
        return service.read(so)

    def _scope(self, stmt):
        """Customer accounts see their customer's orders (whoever placed them); staff see the orders they placed"""
        if self.user.partner_id:
            return stmt.where(DocumentHeader.partner_id == self.user.partner_id)
        return stmt.where(DocumentHeader.created_by == self.user.id)

    def orders(self, status: str | None, skip: int, limit: int) -> list[DocumentHeader]:
        stmt = self._scope(select(DocumentHeader).where(
            DocumentHeader.tenant_id == self.tenant_id,
            DocumentHeader.doc_type == DOC_SO,
            DocumentHeader.is_deleted == false(),
        ))
        if status:
            stmt = stmt.where(DocumentHeader.status == status)
        stmt = stmt.order_by(DocumentHeader.created_at.desc(), DocumentHeader.id.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).unique())

    def _own(self, so_id: uuid.UUID) -> uuid.UUID:
        found = self.db.scalar(self._scope(select(DocumentHeader.id).where(
            DocumentHeader.id == so_id,
            DocumentHeader.tenant_id == self.tenant_id,
            DocumentHeader.doc_type == DOC_SO,
            DocumentHeader.is_deleted == false(),
        )))
        if found is None:
            raise NotFoundError("Order not found")
        return found

    def order(self, so_id: uuid.UUID) -> SalesOrderRead:
        service = SalesOrderService(self.db, self.tenant_id, self.user.id)
        return service.read(service.get(self._own(so_id)))

    def cancel(self, so_id: uuid.UUID) -> SalesOrderRead:
        """The person who ordered may withdraw the order while the warehouse has not confirmed it yet"""
        service = SalesOrderService(self.db, self.tenant_id, self.user.id)
        so = service.get(self._own(so_id))
        if so.status != SO_DRAFT:
            raise DomainError("The warehouse has already confirmed this order; ask them to cancel it")
        return service.read(service.cancel(so.id))
