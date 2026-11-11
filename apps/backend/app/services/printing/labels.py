"""Label PDFs: item and location labels laid out on sheets or rolls as a LabelProfile says.

What a barcode holds is a code the system already resolves when scanned, so printing creates no new data:
- item: its barcode, or the SKU when it has none (PDA and web lookups fall back to the SKU)
- location: its location code
"""

import io
from dataclasses import dataclass, field
from decimal import Decimal

from reportlab.lib.colors import Color
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.schemas.label import LabelLayout
from app.services.printing.pdf import (
    LINE_HEIGHT,
    can_code128,
    draw_code128,
    draw_qr,
    draw_text,
    fit_size,
    wrap,
)

# Fields printed above the bars, bold; the rest go below
_HEADLINE = {"ITEM": "name", "LOCATION": "code"}
_OUTLINE = Color(0.6, 0.6, 0.6)
_GAP = 1 * mm
# Below this the bars are too short to scan reliably, so secondary text is dropped to make room
_MIN_BAR_HEIGHT = 6 * mm

BUILT_IN: dict[str, LabelLayout] = {
    # 24 labels of 70 x 36 mm on A4, the common 3 x 8 office label sheet
    "ITEM": LabelLayout(
        purpose="ITEM", media="SHEET", label_width_mm=Decimal(70), label_height_mm=Decimal(36),
        columns=3, rows=8, margin_top_mm=Decimal("4.5"), margin_left_mm=Decimal(0), gap_x_mm=Decimal(0),
        gap_y_mm=Decimal(0), padding_mm=Decimal(3), barcode_type="CODE128", fields=["name", "barcode_text", "sku"],
        font_size=9,
    ),
    # 10 large labels of 100 x 55 mm on A4: readable from the aisle and easy to scan from below
    "LOCATION": LabelLayout(
        purpose="LOCATION", media="SHEET", label_width_mm=Decimal(100), label_height_mm=Decimal(55),
        columns=2, rows=5, margin_top_mm=Decimal(10), margin_left_mm=Decimal(5), gap_x_mm=Decimal(0),
        gap_y_mm=Decimal(0), padding_mm=Decimal(4), barcode_type="CODE128", fields=["code", "name"], font_size=10,
    ),
}

@dataclass
class LabelContent:
    value: str
    fields: dict[str, str] = field(default_factory=dict)


def sample_labels(purpose: str) -> list[LabelContent]:
    if purpose == "ITEM":
        return [
            LabelContent("6901234567892", {"name": "Sample item name long enough to wrap", "barcode_text": "6901234567892", "sku": "SKU-0001", "uom": "EA", "category": "Category"}),
            LabelContent("SKU-0002", {"name": "Item without barcode (SKU used)", "barcode_text": "SKU-0002", "sku": "SKU-0002", "uom": "CTN", "category": "Category"}),
        ]
    return [
        LabelContent("A-01-02-03", {"code": "A-01-02-03", "name": "Zone A aisle 1 rack 2 level 3", "path": "/WH1/A/A-01/A-01-02/A-01-02-03"}),
        LabelContent("DOCK-IN-1", {"code": "DOCK-IN-1", "name": "Receiving dock 1", "path": "/WH1/DOCK-IN-1"}),
    ]


def render(layout: LabelLayout, labels: list[LabelContent], skip: int = 0, outline: bool = False, title: str = "Labels") -> bytes:
    """One label per page on a roll; sheets fill left to right, top to bottom, after `skip` blank positions."""
    f = float
    w, h = f(layout.label_width_mm) * mm, f(layout.label_height_mm) * mm
    buffer = io.BytesIO()
    if layout.media == "ROLL":
        canvas = Canvas(buffer, pagesize=(w, h))
        canvas.setTitle(title)
        for label in labels:
            _draw_label(canvas, layout, label, 0, 0, w, h, outline)
            canvas.showPage()
    else:
        page_w, page_h = f(layout.page_width_mm) * mm, f(layout.page_height_mm) * mm
        per_page = layout.columns * layout.rows
        canvas = Canvas(buffer, pagesize=(page_w, page_h))
        canvas.setTitle(title)
        slots: list[LabelContent | None] = [None] * (skip % per_page) + list(labels)
        for start in range(0, len(slots), per_page):
            for i, label in enumerate(slots[start : start + per_page]):
                if label is None:
                    continue
                col, row = i % layout.columns, i // layout.columns
                x = (f(layout.margin_left_mm) + col * (f(layout.label_width_mm) + f(layout.gap_x_mm))) * mm
                top = (f(layout.margin_top_mm) + row * (f(layout.label_height_mm) + f(layout.gap_y_mm))) * mm
                _draw_label(canvas, layout, label, x, page_h - top - h, w, h, outline)
            canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _draw_label(canvas: Canvas, layout: LabelLayout, label: LabelContent, x: float, y: float, w: float, h: float, outline: bool) -> None:
    if outline:
        canvas.saveState()
        canvas.setStrokeColor(_OUTLINE)
        canvas.setLineWidth(0.3)
        canvas.setDash(2, 2)
        canvas.rect(x, y, w, h)
        canvas.restoreState()
    pad = float(layout.padding_mm) * mm
    box = (x + pad, y + pad, w - 2 * pad, h - 2 * pad)
    # Code 128 holds printable ASCII only; anything else still prints, as a QR code
    if layout.barcode_type == "QR" or not can_code128(label.value):
        _draw_qr_layout(canvas, layout, label, *box)
    else:
        _draw_bar_layout(canvas, layout, label, *box)


def _texts(layout: LabelLayout, label: LabelContent) -> list[tuple[str, str]]:
    texts = [(name, label.fields[name]) for name in layout.fields if label.fields.get(name)]
    # An item without a barcode is labelled with its SKU: print that once, not as both digits and SKU
    if "barcode_text" in layout.fields and label.fields.get("sku") == label.fields.get("barcode_text"):
        texts = [(name, value) for name, value in texts if name != "sku"]
    return texts


def _draw_bar_layout(canvas: Canvas, layout: LabelLayout, label: LabelContent, x: float, y: float, w: float, h: float) -> None:
    base = float(layout.font_size)
    headline_field = _HEADLINE[layout.purpose]
    texts = _texts(layout, label)
    headline = next((v for k, v in texts if k == headline_field), None)
    digits = next((v for k, v in texts if k == "barcode_text"), None)
    extra = "  ·  ".join(v for k, v in texts if k not in (headline_field, "barcode_text"))

    head_lines: list[str] = []
    head_size = base + 1
    if headline:
        if layout.purpose == "LOCATION":
            head_size = fit_size(headline, True, w, min(h * 0.34, 60))
            head_lines = [headline]
        else:
            head_lines = wrap(headline, True, head_size, w, 2 if h > 22 * mm else 1)

    def bar_height(with_extra: bool) -> float:
        used = len(head_lines) * head_size * LINE_HEIGHT
        used += base * LINE_HEIGHT if digits else 0
        used += base * LINE_HEIGHT if with_extra and extra else 0
        return h - used - _GAP * 2

    show_extra = bool(extra) and bar_height(True) >= _MIN_BAR_HEIGHT
    if bar_height(show_extra) < _MIN_BAR_HEIGHT and len(head_lines) > 1:
        head_lines = head_lines[:1]

    cursor = y + h
    for line in head_lines:
        cursor -= head_size * LINE_HEIGHT
        draw_text(canvas, line, x, cursor + head_size * 0.2, head_size, bold=True, align="center", width=w)

    bottom = y
    if show_extra:
        draw_text(canvas, extra, x, bottom + base * 0.25, base, align="center", width=w)
        bottom += base * LINE_HEIGHT
    if digits:
        draw_text(canvas, digits, x, bottom + base * 0.25, base, align="center", width=w)
        bottom += base * LINE_HEIGHT
    bars = cursor - bottom - _GAP * 2
    if bars > 2 * mm:
        draw_code128(canvas, label.value, x, bottom + _GAP, w, bars)


def _draw_qr_layout(canvas: Canvas, layout: LabelLayout, label: LabelContent, x: float, y: float, w: float, h: float) -> None:
    base = float(layout.font_size)
    texts = _texts(layout, label)
    size = min(h, w * 0.5) if texts else min(w, h)
    draw_qr(canvas, label.value, x, y + (h - size) / 2, size)
    col_x, col_w = x + size + 2 * mm, w - size - 2 * mm
    if not texts or col_w < 10 * mm:
        return
    headline_field = _HEADLINE[layout.purpose]
    cursor = y + h
    for name, value in texts:
        if name == headline_field and layout.purpose == "LOCATION":
            size_pt = fit_size(value, True, col_w, min(h * 0.4, 48))
            lines, bold = [value], True
        elif name == headline_field:
            size_pt, bold = base + 1, True
            lines = wrap(value, True, size_pt, col_w, 3)
        else:
            size_pt, bold, lines = base, False, [value]
        for line in lines:
            if cursor - size_pt * LINE_HEIGHT < y:
                return
            cursor -= size_pt * LINE_HEIGHT
            draw_text(canvas, line, col_x, cursor + size_pt * 0.2, size_pt, bold=bold, width=col_w)
