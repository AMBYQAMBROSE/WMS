import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Unicode,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.business_partner import BusinessPartner
from app.models.item import Item, Uom
from app.models.location import Location
from app.models.reason_code import ReasonCode
from app.models.user import User


class DocNumberRule(Base, TenantScopedMixin):
    __tablename__ = "doc_number_rule"
    __table_args__ = (UniqueConstraint("tenant_id", "doc_type"),)

    doc_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    prefix: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    # Supports {PREFIX} {YYYY} {MM} {DD} {SEQ:n}; the date parts present in the pattern decide whether the sequence resets yearly/monthly/daily
    pattern: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    current_period: Mapped[str] = mapped_column(Unicode(20), default="", nullable=False)
    current_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DocumentHeader(Base, TenantScopedMixin):
    __tablename__ = "document_header"
    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_type", "doc_no"),
        # SQL Server unique constraints allow a single NULL, so use a filtered index that only constrains non-null values
        Index(
            "ux_document_header_client_request",
            "tenant_id",
            "client_request_id",
            unique=True,
            mssql_where=text("client_request_id IS NOT NULL"),
        ),
        # SQL Server does not index foreign keys automatically. Looking up by source document (an order's picks/shipments, a PO's receipts) without an index
        # scans the whole table holding shared locks, blocking and deadlocking with inserts under load (seen in load tests)
        Index("ix_document_header_ref", "ref_document_id"),
        # Document lists: filter by type, page by creation time descending
        Index("ix_document_header_list", "tenant_id", "doc_type", "created_at"),
        # Master data references: deleting a partner/location/reason makes SQL Server check these, and "used by" lookups read them
        Index("ix_document_header_partner", "partner_id"),
        Index("ix_document_header_location", "location_id"),
        Index("ix_document_header_reason", "reason_code_id"),
    )

    doc_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    doc_no: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    status: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    # Client-generated request ID (PDA offline queue): resubmitting the same ID returns the existing document instead of creating another
    client_request_id: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_partner.id"), nullable=True
    )
    # Source document, e.g. a GRN points to its PO, a putaway to its GRN
    ref_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_header.id"), nullable=True
    )
    # Document-level location, e.g. the receiving staging location of a GRN
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location.id"), nullable=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    # For documents that need a reason, such as adjustments
    reason_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reason_code.id"), nullable=True
    )

    partner: Mapped[BusinessPartner | None] = relationship(lazy="joined")
    reason_code: Mapped[ReasonCode | None] = relationship(lazy="joined")
    # Locations covered by a cycle count (including empty ones); frozen for stock movements while counting
    count_locations: Mapped[list["DocumentLocation"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )
    shipment_info: Mapped["ShipmentInfo | None"] = relationship(
        lazy="joined", cascade="all, delete-orphan", uselist=False
    )
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
    __table_args__ = (
        UniqueConstraint("document_id", "line_no"),
        Index("ix_document_line_ref_line", "ref_line_id"),
        # Picker performance is reported by confirmation time; only confirmed lines are indexed
        Index("ix_document_line_confirmed", "confirmed_at", mssql_where=text("confirmed_at IS NOT NULL")),
        # Master data references (see document_header): an unindexed check scans the largest table under shared locks
        Index("ix_document_line_item", "item_id"),
        Index("ix_document_line_from_location", "from_location_id"),
        Index("ix_document_line_to_location", "to_location_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_header.id"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    qty_planned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # PO line: cumulative received quantity; GRN/putaway line: quantity of this document
    qty_actual: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0), nullable=False)
    # Quantity verified by scanning piece by piece (shipment lines: loaded onto the vehicle)
    qty_checked: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal(0), server_default="0", nullable=False
    )
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
    # Time and user of line-by-line confirmation (count line: counted this round; pick line: picked); empty means not done yet
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    document: Mapped[DocumentHeader] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship(lazy="joined")
    uom: Mapped[Uom] = relationship(lazy="joined")
    from_location: Mapped[Location | None] = relationship(
        foreign_keys=[from_location_id], lazy="joined"
    )
    to_location: Mapped[Location | None] = relationship(
        foreign_keys=[to_location_id], lazy="joined"
    )
    count_entries: Mapped[list["CountEntry"]] = relationship(
        order_by="CountEntry.round", lazy="selectin", cascade="all, delete-orphan"
    )
    confirmer: Mapped[User | None] = relationship(foreign_keys=[confirmed_by], lazy="joined")


class ShipmentInfo(Base):
    """Loading details of a shipment (DO), 1:1 extension of document_header (Ninso NormalLoading: driver/plate/seal)"""

    __tablename__ = "shipment_info"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_header.id"), primary_key=True)
    carrier: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    seal_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)


class DocumentLocation(Base, TenantScopedMixin):
    __tablename__ = "document_location"
    __table_args__ = (UniqueConstraint("document_id", "location_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_header.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("location.id"), index=True, nullable=False
    )

    location: Mapped[Location] = relationship(lazy="joined")


class CountEntry(Base, TenantScopedMixin):
    """One record per count round (Ninso Count1/2/3): who counted how much and when; a recount adds a round.
    Resubmitting within a round (PDA offline resend, correction) overwrites that round instead of adding a record.
    """

    __tablename__ = "count_entry"
    __table_args__ = (UniqueConstraint("line_id", "round"),)

    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_line.id"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    counted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    counted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    counter: Mapped[User] = relationship(foreign_keys=[counted_by], lazy="joined")
