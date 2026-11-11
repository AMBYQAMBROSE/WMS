"""Drawing helpers shared by everything the backend prints (labels now, document reports next): fonts that cover the
text, text that fits its box, and barcodes. Units are PDF points unless a name says mm."""

from functools import cache

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.code128 import Code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

LINE_HEIGHT = 1.18
MIN_FONT = 5.0
ELLIPSIS = "…"
# Wider bars look odd and waste the label; narrower than about 0.19 mm is unreadable for most scanners
MAX_BAR_WIDTH = 0.5 * mm
QUIET_MODULES = 10

# Item and partner names are user data and may be in any script. The standard PDF fonts only cover Latin-1, so other
# text uses a CJK font that every PDF viewer provides without embedding a font file.
_UNICODE_FONT = "STSong-Light"


@cache
def _unicode_font() -> str:
    pdfmetrics.registerFont(UnicodeCIDFont(_UNICODE_FONT))
    return _UNICODE_FONT


def font_for(text: str, bold: bool = False) -> str:
    # The standard fonts use WinAnsiEncoding, which is cp1252 (Latin-1 plus typographic marks such as …)
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return _unicode_font()
    return "Helvetica-Bold" if bold else "Helvetica"


def text_width(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def fit_size(text: str, bold: bool, width: float, max_size: float, min_size: float = MIN_FONT) -> float:
    """Largest font size (down to min_size) at which the text fits on one line"""
    font = font_for(text, bold)
    natural = text_width(text, font, max_size)
    if natural <= width or natural == 0:
        return max_size
    return max(min_size, max_size * width / natural)


def truncate(text: str, font: str, size: float, width: float) -> str:
    if text_width(text, font, size) <= width:
        return text
    while text and text_width(text + ELLIPSIS, font, size) > width:
        text = text[:-1]
    return text + ELLIPSIS if text else ""


def wrap(text: str, bold: bool, size: float, width: float, max_lines: int) -> list[str]:
    """Word wrap; a word longer than the line (or text without spaces, such as Chinese) breaks between characters.
    The last line is cut with an ellipsis when the text needs more than max_lines."""
    font = font_for(text, bold)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if text_width(candidate, font, size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        while text_width(word, font, size) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], font, size) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate(lines[-1] + ELLIPSIS, font, size, width)
    return lines


def draw_text(canvas: Canvas, text: str, x: float, y: float, size: float, bold: bool = False, align: str = "left", width: float = 0) -> None:
    """y is the baseline. With a width the text is cut to fit it."""
    font = font_for(text, bold)
    if width:
        text = truncate(text, font, size, width)
    canvas.setFont(font, size)
    if align == "center":
        canvas.drawCentredString(x + width / 2, y, text)
    elif align == "right":
        canvas.drawRightString(x + width, y, text)
    else:
        canvas.drawString(x, y, text)


def can_code128(value: str) -> bool:
    return bool(value) and all(32 <= ord(ch) < 127 for ch in value)


def draw_code128(canvas: Canvas, value: str, x: float, y: float, width: float, height: float) -> float:
    """Code 128 centred in the box, bars as wide as the box allows. Returns the width actually used."""
    modules = Code128(value, barWidth=1, lquiet=QUIET_MODULES, rquiet=QUIET_MODULES, humanReadable=False).width
    bar = min(width / modules, MAX_BAR_WIDTH)
    code = Code128(
        value, barWidth=bar, barHeight=height, lquiet=QUIET_MODULES * bar, rquiet=QUIET_MODULES * bar, humanReadable=False
    )
    code.drawOn(canvas, x + (width - code.width) / 2, y)
    return code.width


def draw_qr(canvas: Canvas, value: str, x: float, y: float, size: float) -> None:
    """QR code (error correction M) as a size x size square with its bottom-left corner at x, y"""
    widget = QrCodeWidget(value, barLevel="M", barBorder=2)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, canvas, x, y)
