"""PDA putaway by sheet: scan the sheet, the item and the bin; a partial put leaves the rest for another bin."""

from playwright.sync_api import Page, expect

from tests.e2e.test_labels import shot
from tests.e2e.test_pda import pda_sign_in, scan
from tests.helpers import Api, balance, make_item, make_warehouse, put_away, receive


def test_put_away_a_sheet_into_two_bins(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bin2 = api.post("/locations", {"code": f"BIN2{unique}", "name": "Bin 2", "location_type": "BIN", "parent_id": wh.warehouse})["id"]
    item = make_item(api, wh, f"PS{unique}")
    # Stock already in BIN makes it the suggested bin for the next receipt
    receive(api, wh, item, 1)
    put_away(api, wh, item, 1)
    grn = receive(api, wh, item, 10)
    sheet = api.get("/putaways", ref_document_id=grn["id"], status="TO_PUT_AWAY")[0]

    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-putaway").click()
    scan(page, "scan-sheet", sheet["doc_no"])
    expect(page.get_by_test_id("target-bin")).to_have_text(f"BIN{unique}")

    # 6 into the suggested bin; the other 4 do not fit
    scan(page, "scan-item", f"PS{unique}")
    scan(page, "scan-bin", f"BIN{unique}")
    page.get_by_test_id("qty").fill("6")
    shot(page, "pda-putaway-qty")
    page.get_by_test_id("confirm-put").click()
    expect(page.get_by_text("4 left, scan the next bin")).to_be_visible(timeout=15_000)

    # The rest into another bin: allowed, with a note that it is not the suggestion
    scan(page, "scan-bin", f"BIN2{unique}")
    expect(page.get_by_text("Not the suggested bin")).to_be_visible()
    expect(page.get_by_test_id("qty")).to_have_value("4")
    page.get_by_test_id("confirm-put").click()

    page.get_by_test_id("finish-putaway").click()
    expect(page.get_by_text(f"Putaway sheet {sheet['doc_no']} done")).to_be_visible(timeout=15_000)
    shot(page, "pda-putaway-done")
    assert api.get(f"/putaways/{sheet['id']}")["status"] == "POSTED"
    assert balance(api, item, wh.bin)[0] == 7
    assert balance(api, item, bin2)[0] == 4
    assert balance(api, item, wh.dock_in)[0] == 0
