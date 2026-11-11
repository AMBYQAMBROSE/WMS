from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin

LABEL_PURPOSES = ("ITEM", "LOCATION")
LABEL_MEDIA = ("SHEET", "ROLL")
BARCODE_TYPES = ("CODE128", "QR")


class LabelProfile(Base, TenantScopedMixin):
    """How one kind of label is laid out on the printer's paper, set up by the user under System > Labels & printing.

    SHEET: a page (A4 by default) cut into columns x rows of equal labels, for office printers and label sheets.
    ROLL: one label per page of exactly label size, for thermal label printers driven through the PDF driver.
    The PDF is the only output today; a direct printer language (ZPL) can be generated later from the same profile.
    One profile per purpose may be the default; printing without choosing a profile uses it (or a built-in layout).
    """

    __tablename__ = "label_profile"

    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    purpose: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    media: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    label_width_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    label_height_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    # Sheet layout only (a roll page is the label itself)
    page_width_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    page_height_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    columns: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_top_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    margin_left_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    gap_x_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    gap_y_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    # Blank space kept inside each label's edge (printers rarely hit the cut exactly)
    padding_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    barcode_type: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    # JSON list of the text fields printed besides the barcode, in order (see app/services/printing/labels.py)
    fields: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    font_size: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
