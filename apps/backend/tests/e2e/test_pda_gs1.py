"""GS1 carton codes and stock labels: one scan gives item, batch, expiry and quantity, nothing is typed."""

from playwright.sync_api import Page, expect

from tests.e2e.test_labels import expect_pdf_tab, shot
from tests.e2e.test_pda import pda_sign_in, scan
from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_warehouse

GS = "\x1d"


def tracked_item(api: Api, wh, unique: str, barcode: str) -> str:
    return api.post("/items", {"sku_code": f"GS{unique}", "name": "GS1 item", "barcode": barcode, "base_uom_id": wh.ea,
                               "is_batch_managed": True, "is_expiry_managed": True})["id"]


def test_receive_from_a_gs1_carton_code(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    ean = f"69{int(unique, 16) % 10**11:011d}"
    item = tracked_item(api, wh, unique, ean)
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 50}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")

    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-receive").click()
    scan(page, "scan-po", po["doc_no"])
    scan(page, "scan-location", f"IN{unique}")
    # GS1-128 as the scanner sends it: symbology identifier, GTIN, expiry, batch ended by GS, count
    scan(page, "scan-item", f"]C101{ean.zfill(14)}17271231" + f"10L{unique}{GS}3024")
    expect(page.get_by_test_id("batch")).to_have_value(f"L{unique}")
    expect(page.get_by_test_id("expiry")).to_have_value("2027-12-31")
    expect(page.get_by_test_id("qty")).to_have_value("24")
    shot(page, "pda-receive-gs1")
    page.get_by_test_id("confirm-entry").click()
    page.get_by_test_id("submit-receive").click()
    expect(page.get_by_text("Received, document no.")).to_be_visible(timeout=15_000)

    [grn] = api.get("/grns", keyword=po["doc_no"])
    line = api.get(f"/grns/{grn['id']}")["lines"][0]
    assert (line["qty_actual"], line["batch_no"], line["expiry_date"]) == (24, f"L{unique}", "2027-12-31")


def test_stock_label_printed_on_the_web_drives_the_putaway(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = tracked_item(api, wh, unique, f"B{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 30}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    lines = [{"po_line_id": po["lines"][0]["id"], "qty": 20, "batch_no": f"A{unique}", "expiry_date": "2027-01-31"},
             {"po_line_id": po["lines"][0]["id"], "qty": 10, "batch_no": f"Z{unique}", "expiry_date": "2027-06-30"}]
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": lines})
    api.post(f"/grns/{grn['id']}/post")

    # Web: print the stock labels of the receipt, 10 per carton
    sign_in(page)
    page.goto(f"/grns/{grn['id']}")
    page.get_by_test_id("print-stock-labels").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_test_id("qty-per-label").fill("10")
    expect_pdf_tab(page, lambda: dialog.get_by_role("button", name="Print").click())

    # PDA: scanning the label of the second batch picks that batch's line and offers the carton quantity
    sheet = api.get("/putaways", ref_document_id=grn["id"], status="TO_PUT_AWAY")[0]
    page.goto(f"{pda_url}/")
    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-putaway").click()
    scan(page, "scan-sheet", sheet["doc_no"])
    scan(page, "scan-item", f"(240)B{unique}(10)Z{unique}(17)270630(30)10")
    scan(page, "scan-bin", f"BIN{unique}")
    expect(page.get_by_test_id("qty")).to_have_value("10")
    page.get_by_test_id("confirm-put").click()
    expect(page.get_by_text(f"GS{unique} 10 into BIN{unique}")).to_be_visible(timeout=15_000)
    done = [line for line in api.get(f"/putaways/{sheet['id']}")["lines"] if line["confirmed_at"]]
    assert [(line["batch_no"], line["qty_actual"]) for line in done] == [(f"Z{unique}", 10)]
