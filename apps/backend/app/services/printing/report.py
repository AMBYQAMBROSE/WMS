"""A4 document reports: the printed copy of a purchase order, receipt, pick list, delivery order and so on.

Every page repeats the title and the document number as a barcode, so any page of a printout can be scanned to open
the document; the footer says when and by whom it was printed and "page x of y". The first page lists the document's
details, then the lines (the table continues across pages with its header repeated), totals, remark and signatures.
"""

import io
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.printing.pdf import UNICODE_FONT, can_code128, draw_code128, draw_text, font_for

MARGIN = 14 * mm
HEADER_HEIGHT = 24 * mm
FOOTER_HEIGHT = 10 * mm
BODY_SIZE = 8.5
INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d1d5db")
SHADE = colors.HexColor("#f3f4f6")
_ALIGN = {"L": TA_LEFT, "R": TA_RIGHT, "C": TA_CENTER}


@dataclass
class Column:
    title: str
    # Share of the table width; the widths of all columns are scaled to fill the page
    weight: float
    align: str = "L"


@dataclass
class BarcodeCell:
    """A table cell holding a scannable barcode with text under it (item or bin on a putaway sheet or pick list)"""

    value: str
    caption: str


class _Bars(Flowable):
    """Code 128 as wide as its table cell allows"""

    HEIGHT = 7 * mm
    MAX_WIDTH = 45 * mm

    def __init__(self, value: str):
        super().__init__()
        self.value = value
        self.width = 0

    def wrap(self, available_width, available_height):
        self.width = available_width
        return available_width, self.HEIGHT

    def draw(self):
        # Capped and centred: a barcode across a wide column is harder to aim at among its neighbours in the row
        width = min(self.width, self.MAX_WIDTH)
        draw_code128(self.canv, self.value, (self.width - width) / 2, 0, width, self.HEIGHT)


Cell = str | BarcodeCell


@dataclass
class Report:
    title: str
    doc_no: str
    status: str
    company: str
    printed: str
    info: list[tuple[str, str]]
    columns: list[Column]
    rows: list[list[Cell]]
    totals: str = ""
    remark: str = ""
    signatures: list[str] = field(default_factory=list)
    # A sentence printed above the signatures, e.g. what the customer confirms by signing
    declaration: str = ""
    # Big diagonal word over every page (CANCELLED, DRAFT); empty for a normal copy
    watermark: str = ""
    empty_text: str = "No lines"


def _style(text: str, size: float = BODY_SIZE, bold: bool = False, align: str = "L", color=INK) -> ParagraphStyle:
    font = font_for(text, bold)
    return ParagraphStyle(
        "cell", fontName=font, fontSize=size, leading=size * 1.25, alignment=_ALIGN[align], textColor=color,
        # Text without spaces (Chinese, long codes) may break between characters
        wordWrap="CJK" if font == UNICODE_FONT else None, splitLongWords=True,
    )


def para(text: str, size: float = BODY_SIZE, bold: bool = False, align: str = "L", color=INK) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), _style(text or "", size, bold, align, color))


def render(report: Report) -> bytes:
    buffer = io.BytesIO()
    width, height = A4
    # The page frame pads its content by 6 pt on every side; margins are shrunk by that so text and tables line up
    # with the header and footer drawn at MARGIN
    pad = 6
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=f"{report.title} {report.doc_no}",
        leftMargin=MARGIN - pad, rightMargin=MARGIN - pad,
        topMargin=MARGIN + HEADER_HEIGHT - pad, bottomMargin=MARGIN + FOOTER_HEIGHT - pad,
    )
    body_width = width - 2 * MARGIN
    story: list = [_info_table(report.info, body_width), Spacer(0, 5 * mm), _lines_table(report, body_width)]
    if report.totals:
        story += [Spacer(0, 2 * mm), para(report.totals, bold=True, align="R")]
    if report.remark:
        story += [Spacer(0, 4 * mm), para("Remark", 7.5, color=MUTED), para(report.remark)]
    if report.signatures:
        story.append(Spacer(0, 8 * mm))
        block = []
        if report.declaration:
            block += [para(report.declaration), Spacer(0, 3 * mm)]
        block.append(_signatures(report.signatures, body_width))
        story.append(KeepTogether(block))

    def page(canvas: Canvas, _doc) -> None:
        _draw_page(canvas, report, width, height)

    doc.build(story, onFirstPage=page, onLaterPages=page, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


def _info_table(info: list[tuple[str, str]], width: float) -> Table:
    """Label/value pairs in two columns, filled down the left column first"""
    pairs = [(label, value) for label, value in info if value]
    half = (len(pairs) + 1) // 2
    left, right = pairs[:half], pairs[half:]
    rows = []
    for i in range(half):
        row = []
        for side in (left, right):
            if i < len(side):
                row += [para(side[i][0], 7.5, color=MUTED), para(side[i][1])]
            else:
                row += ["", ""]
        rows.append(row)
    label_w, value_w = 0.14 * width, 0.36 * width
    table = Table(rows or [[""]], colWidths=[label_w, value_w, label_w, value_w] if rows else [width])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _lines_table(report: Report, width: float) -> Table:
    total = sum(c.weight for c in report.columns)
    widths = [width * c.weight / total for c in report.columns]
    header = [para(c.title, 7.5, bold=True, align=c.align) for c in report.columns]
    body = [[_cell(value, col) for value, col in zip(row, report.columns, strict=True)] for row in report.rows]
    if not body:
        body = [[para(report.empty_text, color=MUTED)] + [""] * (len(report.columns) - 1)]
    table = Table([header, *body], colWidths=widths, repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), SHADE),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if not report.rows:
        style.append(("SPAN", (0, 1), (-1, 1)))
    table.setStyle(TableStyle(style))
    return table


def _cell(value: Cell, column: Column):
    if isinstance(value, BarcodeCell):
        caption = para(value.caption, 7.5, align="C")
        return [_Bars(value.value), caption] if can_code128(value.value) else caption
    return para(value, align=column.align)


def _signatures(roles: list[str], width: float) -> Table:
    cell_w = width / len(roles)
    cells = [[para(role, 7.5, color=MUTED) for role in roles], ["" for _ in roles], [para("Name / Date", 7, color=MUTED) for _ in roles]]
    table = Table(cells, colWidths=[cell_w] * len(roles), rowHeights=[None, 14 * mm, None])
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def _draw_page(canvas: Canvas, report: Report, width: float, height: float) -> None:
    top = height - MARGIN
    left, right = MARGIN, width - MARGIN
    canvas.saveState()
    canvas.setFillColor(MUTED)
    draw_text(canvas, report.company, left, top - 8, 8, width=right - left - 70 * mm)
    canvas.setFillColor(INK)
    draw_text(canvas, report.title, left, top - 24, 17, bold=True, width=right - left - 70 * mm)
    canvas.setFillColor(MUTED)
    draw_text(canvas, f"Status: {report.status}", left, top - 36, 8.5)

    # Document number as text and barcode, top right: scanning it opens the document on the PDA and in the web app
    box_w = 66 * mm
    canvas.setFillColor(INK)
    draw_text(canvas, report.doc_no, right - box_w, top - 9, 11, bold=True, align="right", width=box_w)
    if can_code128(report.doc_no):
        draw_code128(canvas, report.doc_no, right - box_w, top - HEADER_HEIGHT + 4 * mm, box_w, 11 * mm)
    canvas.setStrokeColor(INK)
    canvas.setLineWidth(1)
    canvas.line(left, top - HEADER_HEIGHT + 1.5 * mm, right, top - HEADER_HEIGHT + 1.5 * mm)

    if report.watermark:
        canvas.saveState()
        canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
        canvas.translate(width / 2, height / 2)
        canvas.rotate(35)
        canvas.setFont("Helvetica-Bold", 90)
        canvas.drawCentredString(0, -30, report.watermark)
        canvas.restoreState()

    canvas.setFillColor(MUTED)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(left, MARGIN + 5 * mm, right, MARGIN + 5 * mm)
    draw_text(canvas, report.printed, left, MARGIN + 1.5 * mm, 7.5, width=right - left - 30 * mm)
    canvas.restoreState()


class _NumberedCanvas(Canvas):
    """Holds pages back until the end so each footer can say "page x of y" """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self):  # noqa: N802 (reportlab's name)
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.saveState()
            self.setFillColor(MUTED)
            self.setFont("Helvetica", 7.5)
            self.drawRightString(A4[0] - MARGIN, MARGIN + 1.5 * mm, f"Page {self._pageNumber} of {count}")
            self.restoreState()
            super().showPage()
        super().save()
