from decimal import Decimal


def qty_text(value: Decimal) -> str:
    """Quantity for messages: 10 not 1E+1 (what Decimal.normalize() alone gives), 10.5 not 10.5000"""
    return format(value.normalize(), "f")
