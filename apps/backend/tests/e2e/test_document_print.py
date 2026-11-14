"""Printing documents from the web app: the Print button on a document, the printout that opens by itself after
posting, and receiving in one click (create and post) with the receipt and its putaway sheet ready to print."""

from playwright.sync_api import Page, expect

from tests.e2e.test_labels import expect_pdf_preview, shot
from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_item, make_warehouse

# These tests are about the preview that opens after posting: keep it on (see conftest)
PRINT_PREVIEW = True


def _confirmed_po(api: Api, wh, item: str, qty: int = 4) -> dict:
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    return po


def test_print_a_document_and_print_after_posting(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"PRN{unique}")
    po = _confirmed_po(api, wh, item)
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 4}]})

    sign_in(page)
    page.goto(f"/purchase-orders/{po['id']}")
    expect_pdf_preview(page, lambda: page.get_by_test_id("print-document").click(), method="GET")

    # Posting brings up the printout without another click: the receipt, and the putaway sheet that posting into the
    # dock made, a tab each
    page.goto(f"/grns/{grn['id']}")
    page.get_by_role("button", name="Post", exact=True).click()
    with page.expect_response(lambda r: f"/documents/{grn['id']}/print" in r.url):
        page.get_by_role("button", name="OK").click()
    sheet = api.get("/putaways", ref_document_id=grn["id"], status="TO_PUT_AWAY")[0]
    expect_pdf_preview(page, tabs=[grn["doc_no"], sheet["doc_no"]], shot_as="print-after-post")
    # The print is in the document's history
    assert [log["action"] for log in api.get("/audit-logs", entity_id=grn["id"], action="PRINT")] == ["PRINT"]


    page.get_by_role("button", name=f"Putaway sheet {sheet['doc_no']}").click()
    expect(page.get_by_text("Putaway sheet", exact=True)).to_be_visible()
    expect(page.get_by_test_id("put-1")).to_be_visible()
    shot(page, "putaway-sheet-web")
    assert not errors


def test_receive_in_one_click_and_switch_the_preview_off(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"ONE{unique}")
    po = _confirmed_po(api, wh, item)
    dock = api.get(f"/locations/{wh.dock_in}")

    sign_in(page)
    page.goto(f"/grns/new?po={po['id']}")
    receiving = page.get_by_label("Receiving location")
    receiving.fill(dock["code"])
    page.get_by_title(f"{dock['code']} {dock['name']}").click()
    # Create and post: the receipt is posted and its printout opens, with the putaway sheet
    with page.expect_response(lambda r: "/print" in r.url and r.request.method == "GET"):
        page.get_by_test_id("create-and-post").click()
    grn = api.get("/grns", po_id=po["id"])[0]
    assert grn["status"] == "POSTED"
    sheet = api.get("/putaways", ref_document_id=grn["id"], status="TO_PUT_AWAY")[0]
    expect(page.get_by_test_id("print-preview-print")).to_be_focused()
    for doc in (grn, sheet):
        expect(page.get_by_role("tab", name=doc["doc_no"])).to_be_visible()
    shot(page, "create-and-post")
    # Whoever does not print switches the preview off, there and then
    page.get_by_test_id("print-after-posting").uncheck()
    page.locator(".wms-print-footer").get_by_role("button", name="Close").click()
    expect(page).to_have_url(f"{page.url.split('/grns/')[0]}/grns/{grn['id']}")

    # The next receipt starts with the dock used last time, and posting it leaves the page alone
    po2 = _confirmed_po(api, wh, item)
    page.goto(f"/grns/new?po={po2['id']}")
    expect(page.get_by_title(f"{dock['code']} {dock['name']}")).to_be_visible()
    page.get_by_test_id("create-and-post").click()
    # The message offers both printouts instead: one click brings up the preview
    expect(page.get_by_test_id("print-made-by-post")).to_be_visible()
    expect(page.get_by_test_id("print-preview-print")).to_be_hidden()
    assert api.get("/grns", po_id=po2["id"])[0]["status"] == "POSTED"
    expect_pdf_preview(page, page.get_by_test_id("print-after-post").click, method="GET")
    assert not errors
