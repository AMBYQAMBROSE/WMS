"""Label profiles and label PDFs."""

import re

from tests.helpers import PREFIX, Api

SHEET_3X8 = {
    "purpose": "ITEM", "media": "SHEET", "label_width_mm": 70, "label_height_mm": 36,
    "columns": 3, "rows": 8, "margin_top_mm": 4.5, "margin_left_mm": 0, "gap_x_mm": 0, "gap_y_mm": 0,
    "barcode_type": "CODE128", "fields": ["name", "barcode_text", "sku"], "font_size": 9,
}
ROLL_50X30 = {
    "purpose": "ITEM", "media": "ROLL", "label_width_mm": 50, "label_height_mm": 30,
    "margin_top_mm": 0, "margin_left_mm": 0, "gap_x_mm": 0, "gap_y_mm": 0,
    "barcode_type": "QR", "fields": ["name", "sku", "uom"], "font_size": 8,
}


def pages(pdf: bytes) -> int:
    assert pdf.startswith(b"%PDF"), pdf[:200]
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


def print_pdf(client, headers, path: str, body: dict, expect: int = 200) -> bytes:
    response = client.post(PREFIX + path, json=body, headers=headers)
    assert response.status_code == expect, response.text
    if expect == 200:
        assert response.headers["content-type"] == "application/pdf"
    return response.content


def make_items(api: Api, unique: str, count: int) -> list[str]:
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    ids = []
    for i in range(count):
        # Every other item has no barcode: its label carries the SKU
        body = {"sku_code": f"LBL{unique}{i}", "name": f"Label test item {i}", "base_uom_id": ea}
        if i % 2 == 0:
            body["barcode"] = f"69{unique}{i}"
        ids.append(api.post("/items", body)["id"])
    return ids


def test_item_labels_fill_sheets_after_skipped_positions(client, admin_headers, unique):
    api = Api(client, admin_headers)
    profile = api.post("/label-profiles", {**SHEET_3X8, "name": f"Sheet {unique}"})
    items = make_items(api, unique, 2)

    body = {"item_ids": items, "copies": 2, "profile_id": profile["id"]}
    assert pages(print_pdf(client, admin_headers, "/labels/items", body)) == 1
    # 22 used positions + 4 labels = 26 > 24 per sheet
    assert pages(print_pdf(client, admin_headers, "/labels/items", {**body, "skip": 22})) == 2


def test_roll_prints_one_label_per_page(client, admin_headers, unique):
    api = Api(client, admin_headers)
    profile = api.post("/label-profiles", {**ROLL_50X30, "name": f"Roll {unique}"})
    items = make_items(api, unique, 3)
    pdf = print_pdf(client, admin_headers, "/labels/items", {"item_ids": items, "copies": 2, "profile_id": profile["id"]})
    assert pages(pdf) == 6


def test_text_outside_latin_and_non_ascii_barcodes_print(client, admin_headers, unique):
    api = Api(client, admin_headers)
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    item = api.post("/items", {"sku_code": f"CJK{unique}", "name": "测试商品 名称很长需要换行显示", "barcode": f"条码{unique}", "base_uom_id": ea})
    # Code 128 cannot hold the barcode, so that label falls back to a QR code instead of failing
    assert pages(print_pdf(client, admin_headers, "/labels/items", {"item_ids": [item["id"]]})) == 1


def test_layout_must_fit_the_page(client, admin_headers, unique):
    api = Api(client, admin_headers)
    too_wide = {**SHEET_3X8, "name": f"Wide {unique}", "label_width_mm": 71}
    api.post("/label-profiles", too_wide, expect=422)
    api.post("/label-profiles", {**SHEET_3X8, "name": f"Bad {unique}", "fields": ["code"]}, expect=422)
    api.post("/label-profiles", {**SHEET_3X8, "name": f"Pad {unique}", "padding_mm": 20}, expect=422)


def test_one_default_per_purpose(client, admin_headers, unique):
    api = Api(client, admin_headers)
    first = api.post("/label-profiles", {**SHEET_3X8, "name": f"Default A {unique}", "is_default": True})
    second = api.post("/label-profiles", {**ROLL_50X30, "name": f"Default B {unique}", "is_default": True})
    try:
        defaults = [p["id"] for p in api.get("/label-profiles", purpose="ITEM") if p["is_default"]]
        assert defaults == [second["id"]]
        # Printing without a profile uses the default: the roll, one page per label
        items = make_items(api, unique, 2)
        assert pages(print_pdf(client, admin_headers, "/labels/items", {"item_ids": items})) == 2
    finally:
        for profile in (first, second):
            api.call("DELETE", f"/label-profiles/{profile['id']}")


def test_profile_edit_checks_version(client, admin_headers, unique):
    api = Api(client, admin_headers)
    profile = api.post("/label-profiles", {**SHEET_3X8, "name": f"Edit {unique}"})
    edited = api.call("PUT", f"/label-profiles/{profile['id']}", {**SHEET_3X8, "name": f"Edited {unique}", "row_version": profile["row_version"]})
    assert edited["name"] == f"Edited {unique}"
    api.call("PUT", f"/label-profiles/{profile['id']}", {**SHEET_3X8, "name": "Stale", "row_version": profile["row_version"]}, expect=409)


def test_location_labels_for_everything_under_a_parent(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = api.post("/locations", {"code": f"LW{unique}", "name": "W", "location_type": "WAREHOUSE"})
    zone = api.post("/locations", {"code": f"LZ{unique}", "name": "Z", "location_type": "ZONE", "parent_id": wh["id"]})
    for i in range(12):
        api.post("/locations", {"code": f"LB{unique}-{i:02d}", "name": f"Bin {i}", "location_type": "BIN", "parent_id": zone["id"]})
    api.post("/locations", {"code": f"LD{unique}", "name": "Dock", "location_type": "DOCK", "parent_id": wh["id"]})

    # The built-in layout has 10 per sheet (unless a default profile was set by someone else)
    locations = {"purpose": "LOCATION", "media": "SHEET", "label_width_mm": 100, "label_height_mm": 55, "columns": 2, "rows": 5,
                 "margin_top_mm": 10, "margin_left_mm": 5, "gap_x_mm": 0, "gap_y_mm": 0, "fields": ["code", "name"], "name": f"Loc {unique}"}
    profile = api.post("/label-profiles", locations)
    assert pages(print_pdf(client, admin_headers, "/labels/locations", {"parent_id": zone["id"], "profile_id": profile["id"]})) == 2
    # The whole warehouse: 12 bins + 1 dock, not the zone itself
    assert pages(print_pdf(client, admin_headers, "/labels/locations", {"parent_id": wh["id"], "profile_id": profile["id"], "skip": 8})) == 3

    # An item profile cannot print location labels
    item_profile = api.post("/label-profiles", {**SHEET_3X8, "name": f"Item {unique}"})
    print_pdf(client, admin_headers, "/labels/locations", {"parent_id": zone["id"], "profile_id": item_profile["id"]}, expect=400)
    print_pdf(client, admin_headers, "/labels/locations", {"profile_id": profile["id"]}, expect=422)


def test_test_print_outlines_a_full_sheet(client, admin_headers, unique):
    pdf = print_pdf(client, admin_headers, "/label-profiles/test-print", SHEET_3X8)
    assert pages(pdf) == 1
    assert pages(print_pdf(client, admin_headers, "/label-profiles/test-print", ROLL_50X30)) == 3


def test_stock_labels_per_carton_of_a_receipt(client, admin_headers, unique):
    from datetime import date
    from decimal import Decimal

    from app.services.printing.labels import stock_code
    from tests.helpers import make_warehouse

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = api.post("/items", {"sku_code": f"STK{unique}", "name": "Batch item", "base_uom_id": wh.ea,
                               "is_batch_managed": True, "is_expiry_managed": True})["id"]
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 50}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": [
        {"po_line_id": po["lines"][0]["id"], "qty": 50, "batch_no": f"L{unique}", "expiry_date": "2027-05-31"}]})
    print_pdf(client, admin_headers, "/labels/stock", {"grn_id": grn["id"]}, expect=400)  # not posted yet
    api.post(f"/grns/{grn['id']}/post")

    roll = {**ROLL_50X30, "purpose": "STOCK", "barcode_type": "QR", "fields": ["sku", "batch", "expiry", "qty"], "name": f"Stock {unique}"}
    profile = api.post("/label-profiles", roll)
    # Cartons of 24: 24 + 24 + 2, one label (page on a roll) each
    body = {"grn_id": grn["id"], "qty_per_label": 24, "profile_id": profile["id"]}
    assert pages(print_pdf(client, admin_headers, "/labels/stock", body)) == 3
    assert pages(print_pdf(client, admin_headers, "/labels/stock", {"grn_id": grn["id"]})) == 1  # built-in A4 layout

    # The code the PDA reads: printable GS1 element string
    assert stock_code("SKU-1", "L1", date(2027, 5, 31), Decimal(24)) == "(240)SKU-1(10)L1(17)270531(30)24"
    assert stock_code("SKU-1", None, None, Decimal("2.5")) == "(240)SKU-1"
