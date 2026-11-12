"""Printing documents from the web app: the Print button on a document, and the print link offered after posting."""

from playwright.sync_api import Page, expect

from tests.e2e.test_labels import expect_pdf_tab, shot
from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_item, make_warehouse


def test_print_a_document_and_print_after_posting(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"PRN{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 4}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 4}]})

    sign_in(page)
    page.goto(f"/purchase-orders/{po['id']}")
    expect_pdf_tab(page, lambda: page.get_by_test_id("print-document").click(), method="GET")

    page.goto(f"/grns/{grn['id']}")
    page.get_by_role("button", name="Post", exact=True).click()
    page.get_by_role("button", name="OK").click()
    link = page.get_by_test_id("print-after-post")
    expect(link).to_be_visible()
    shot(page, "print-after-post")
    expect_pdf_tab(page, link.click, method="GET")
    # The print is in the document's history
    assert [log["action"] for log in api.get("/audit-logs", entity_id=grn["id"], action="PRINT")] == ["PRINT"]

    # Posting into the dock made a putaway sheet: offered for printing too, and linked from the receipt
    sheet = api.get("/putaways", ref_document_id=grn["id"], status="TO_PUT_AWAY")[0]
    expect(page.get_by_test_id("print-made-by-post")).to_have_text(f"Print {sheet['doc_no']}")
    page.get_by_role("button", name=f"Putaway sheet {sheet['doc_no']}").click()
    expect(page.get_by_text("Putaway sheet", exact=True)).to_be_visible()
    expect(page.get_by_test_id("put-1")).to_be_visible()
    shot(page, "putaway-sheet-web")
    assert not errors
