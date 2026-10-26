import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.business_partner import BusinessPartner
from app.models.item import Item, Uom
from app.models.location import Location


class DocNumberRule(Base, TenantScopedMixin):
    __tablename__ = "doc_number_rule"
    __table_args__ = (UniqueConstraint("tenant_id", "doc_type"),)

    doc_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    prefix: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    # 支持 {PREFIX} {YYYY} {MM} {DD} {SEQ:n}；模板里出现的日期部分决定序号按年/月/日重置
    pattern: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    current_period: Mapped[str] = mapped_column(Unicode(20), default="", nullable=False)
    current_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DocumentHeader(Base, TenantScopedMixin):
    __tablename__ = "document_header"
    __table_args__ = (UniqueConstraint("tenant_id", "doc_type", "doc_no"),)

    doc_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    doc_no: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    status: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_partner.id"), nullable=True
    )
    # 来源单据，如 GRN 指向 PO、上架单指向 GRN
    ref_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_header.id"), nullable=True
    )
    # 单据级仓位，如 GRN 的收货暂存位
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location.id"), nullable=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)

    partner: Mapped[BusinessPartner | None] = relationship(lazy="joined")
    location: Mapped[Location | None] = relationship(lazy="joined")
    ref_document: Mapped["DocumentHeader | None"] = relationship(
        remote_side="DocumentHeader.id", lazy="joined"
    )
    lines: Mapped[list["DocumentLine"]] = relationship(
        back_populates="document",
        order_by="DocumentLine.line_no",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class DocumentLine(Base, TenantScopedMixin):
    __tablename__ = "document_line"
    __table_args__ = (UniqueConstraint("document_id", "line_no"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_header.id"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    qty_planned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # PO 行：累计已收数量；GRN/上架行：本单实际数量
    qty_actual: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0), nullable=False)
    batch_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id"), nullable=True
    )
    to_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id"), nullable=True
    )
    ref_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_line.id"), nullable=True
    )

    document: Mapped[DocumentHeader] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship(lazy="joined")
    uom: Mapped[Uom] = relationship(lazy="joined")
    from_location: Mapped[Location | None] = relationship(
        foreign_keys=[from_location_id], lazy="joined"
    )
    to_location: Mapped[Location | None] = relationship(
        foreign_keys=[to_location_id], lazy="joined"
    )
