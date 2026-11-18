import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.item import Item, Uom


class Recipe(Base, TenantScopedMixin):
    """Recipe / bill of materials (feature RECIPES): the components that make `output_qty` base units of a product.
    Used for costing (cost per unit from purchase prices) and to see how much current stock can make; it does not move stock."""

    __tablename__ = "recipe"
    __table_args__ = (UniqueConstraint("tenant_id", "code"), Index("ix_recipe_product", "tenant_id", "product_item_id"))

    code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    product_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    # Batch size the component quantities are for, in the product's base unit (e.g. 10 cakes per batch)
    output_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    remark: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[Item] = relationship(lazy="joined")
    lines: Mapped[list["RecipeLine"]] = relationship(
        back_populates="recipe", order_by="RecipeLine.line_no", lazy="selectin", cascade="all, delete-orphan"
    )


class RecipeLine(Base, TenantScopedMixin):
    __tablename__ = "recipe_line"
    __table_args__ = (Index("ix_recipe_line_recipe", "recipe_id"), Index("ix_recipe_line_item", "item_id"))

    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipe.id"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship(lazy="joined")
    uom: Mapped[Uom] = relationship(lazy="joined")
