/**
 * GS1 element strings: one scan of a supplier's GS1-128 / GS1 DataMatrix / GS1 QR carton code, or of our own stock
 * label, gives the item and its batch, expiry and quantity, so none of them is typed.
 *
 * Accepted forms:
 * - raw, as a scanner sends it: "0106901234567892" "17261231" "10L123" with a GS character (ASCII 29) ending each
 *   variable-length field, optionally behind a symbology identifier such as "]C1" (GS1-128), "]d2" (DataMatrix),
 *   "]Q3" (QR). Scanners must be set to transmit GS (FNC1) and identifiers; see docs/scanner-setup.md.
 * - human readable with parentheses: "(01)06901234567892(17)261231(10)L123". Our stock labels use this form: it
 *   is plain printable text, so it survives any scanner setting.
 * Item identification: AI 01 (GTIN) or AI 240 (additional item id: our labels put the item barcode or SKU there).
 */

export interface Gs1Data {
  gtin: string | null;
  /** AI 240: item barcode or SKU (our stock labels) */
  itemCode: string | null;
  batch: string | null;
  /** YYYY-MM-DD */
  expiry: string | null;
  /** AI 30 / 37: count of items */
  qty: number | null;
}

const GS = "\u001d";
/** Fixed-length AIs (data length) */
const FIXED: Record<string, number> = { "00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2 };
/** Variable-length AIs (maximum data length), ended by GS or the end of the code */
const VARIABLE: Record<string, number> = { "10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "240": 30, "241": 30, "250": 30, "400": 30, "90": 30 };
const SYMBOLOGY = /^\][A-Za-z][0-9]/;
const GS1_SYMBOLOGIES = new Set(["]C1", "]e0", "]d2", "]Q3", "]J1"]);

/** YYMMDD -> YYYY-MM-DD; day 00 means the last day of the month (GS1 rule) */
function gs1Date(value: string): string | null {
  if (!/^\d{6}$/.test(value)) return null;
  const year = 2000 + Number(value.slice(0, 2));
  const month = Number(value.slice(2, 4));
  let day = Number(value.slice(4, 6));
  if (month < 1 || month > 12) return null;
  if (day === 0) day = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCMonth() !== month - 1) return null;
  return date.toISOString().slice(0, 10);
}

/** Element strings as [AI, data] pairs, or null when the code is not GS1 */
function elements(raw: string): [string, string][] | null {
  let code = raw.trim();
  let marked = false;
  if (SYMBOLOGY.test(code)) {
    marked = GS1_SYMBOLOGIES.has(code.slice(0, 3));
    code = code.slice(3);
  }
  if (code.startsWith("(")) {
    const pairs: [string, string][] = [];
    const pattern = /\((\d{2,4})\)([^(]*)/g;
    let consumed = 0;
    for (let m = pattern.exec(code); m; m = pattern.exec(code)) {
      if (m.index !== consumed) return null;
      pairs.push([m[1], m[2].replace(new RegExp(GS, "g"), "")]);
      consumed = pattern.lastIndex;
    }
    return consumed === code.length && pairs.length ? pairs : null;
  }
  if (code.startsWith(GS)) code = code.slice(1);
  // Without a GS1 symbology identifier or a GS character, only a code that starts with a GTIN is taken as GS1,
  // so ordinary barcodes (EAN-13, internal codes) are never misread
  if (!marked && !code.includes(GS) && !/^01\d{14}\d{2}/.test(code)) return null;

  const pairs: [string, string][] = [];
  let i = 0;
  while (i < code.length) {
    let ai: string | null = null;
    for (const length of [2, 3, 4]) {
      const candidate = code.slice(i, i + length);
      if (candidate in FIXED || candidate in VARIABLE) {
        ai = candidate;
        break;
      }
      // 310n-369n: measures with the decimal position in the 4th digit, 6 digits of data
      if (length === 4 && /^3[1-6]\d\d$/.test(candidate)) {
        ai = candidate;
        break;
      }
    }
    if (!ai) return pairs.length ? pairs : null;
    i += ai.length;
    if (ai in FIXED || /^3[1-6]\d\d$/.test(ai)) {
      const length = FIXED[ai] ?? 6;
      pairs.push([ai, code.slice(i, i + length)]);
      i += length;
      if (code[i] === GS) i += 1;
    } else {
      const end = code.indexOf(GS, i);
      const stop = Math.min(end === -1 ? code.length : end, i + VARIABLE[ai]);
      pairs.push([ai, code.slice(i, stop)]);
      i = end === -1 || end > stop ? stop : end + 1;
    }
  }
  return pairs;
}

export function parseGs1(raw: string): Gs1Data | null {
  const pairs = elements(raw);
  if (!pairs) return null;
  const get = (ai: string) => pairs.find(([key]) => key === ai)?.[1] ?? null;
  const gtin = get("01") ?? get("02");
  const itemCode = get("240");
  if (!gtin && !itemCode) return null;
  const count = get("30") ?? get("37");
  const qty = count !== null && /^\d+$/.test(count) ? Number(count) : null;
  return {
    gtin,
    itemCode,
    batch: get("10"),
    expiry: gs1Date(get("17") ?? "") ?? null,
    qty: qty && qty > 0 ? qty : null,
  };
}

/** The forms a GTIN-14 may be stored in as an item barcode: as is, EAN-13, UPC-A (leading zeros dropped) */
export function gtinCandidates(gtin: string): string[] {
  const out = [gtin];
  for (let s = gtin; s.startsWith("0") && s.length > 8; ) {
    s = s.slice(1);
    out.push(s);
  }
  return out;
}

