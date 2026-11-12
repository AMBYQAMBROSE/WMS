"""GS1 element strings (supplier carton codes, our stock labels), read the same way as the PDA does
(apps/mobile/src/lib/gs1.ts): so scanning such a code into a web item field finds the item too."""

import re
from dataclasses import dataclass

GS = "\x1d"
_FIXED = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2}
_VARIABLE = {"10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "240": 30, "241": 30, "250": 30, "400": 30, "90": 30}
_SYMBOLOGY = re.compile(r"^\][A-Za-z][0-9]")
_GS1_SYMBOLOGIES = {"]C1", "]e0", "]d2", "]Q3", "]J1"}
_MEASURE = re.compile(r"^3[1-6]\d\d$")


@dataclass
class Gs1:
    gtin: str | None
    item_code: str | None
    batch: str | None

    def item_keys(self) -> list[str]:
        """Item barcodes or SKUs this code may stand for: AI 240, the GTIN, and the GTIN without leading zeros
        (EAN-13 / UPC-A stored as the item barcode)"""
        keys = [self.item_code] if self.item_code else []
        if self.gtin:
            keys.append(self.gtin)
            short = self.gtin
            while short.startswith("0") and len(short) > 8:
                short = short[1:]
                keys.append(short)
        return keys


def _elements(raw: str) -> list[tuple[str, str]] | None:
    code = raw.strip()
    marked = False
    if _SYMBOLOGY.match(code):
        marked = code[:3] in _GS1_SYMBOLOGIES
        code = code[3:]
    if code.startswith("("):
        pairs = re.findall(r"\((\d{2,4})\)([^(]*)", code)
        rebuilt = "".join(f"({ai}){value}" for ai, value in pairs)
        return [(ai, value.replace(GS, "")) for ai, value in pairs] if pairs and rebuilt == code else None
    code = code.lstrip(GS)
    if not marked and GS not in code and not re.match(r"^01\d{16}", code):
        return None
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(code):
        ai = next((code[i : i + n] for n in (2, 3, 4) if code[i : i + n] in _FIXED or code[i : i + n] in _VARIABLE
                   or (n == 4 and _MEASURE.match(code[i : i + n]))), None)
        if ai is None:
            return pairs or None
        i += len(ai)
        if ai in _FIXED or _MEASURE.match(ai):
            length = _FIXED.get(ai, 6)
            pairs.append((ai, code[i : i + length]))
            i += length
            if code[i : i + 1] == GS:
                i += 1
        else:
            end = code.find(GS, i)
            stop = min(len(code) if end == -1 else end, i + _VARIABLE[ai])
            pairs.append((ai, code[i:stop]))
            i = stop if end == -1 or end > stop else end + 1
    return pairs


def parse(raw: str) -> Gs1 | None:
    pairs = _elements(raw)
    if not pairs:
        return None
    values = dict(pairs)
    gtin = values.get("01") or values.get("02")
    item_code = values.get("240")
    if not gtin and not item_code:
        return None
    return Gs1(gtin=gtin, item_code=item_code, batch=values.get("10"))
