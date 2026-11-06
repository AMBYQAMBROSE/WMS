"""Optimistic locking in the browser: saving over a colleague's newer change is refused with a clear message."""

from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_item, make_warehouse


def test_saving_an_outdated_order_form_is_refused(page: Page, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"EV{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})

    sign_in(page)
    page.goto(f"/purchase-orders/{po['id']}/edit")
    expect(page.get_by_text(f"S{unique}").first).to_be_visible()  # the form is filled from the draft

    # A colleague saves first; live updates refresh this page's data meanwhile, but the form keeps its version
    api.call("PUT", f"/purchase-orders/{po['id']}", {
        "partner_id": wh.supplier, "remark": "colleague", "row_version": po["row_version"],
        "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 7}],
    })
    page.wait_for_timeout(3_000)  # let a live refresh arrive

    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("changed by someone else")).to_be_visible()
    saved = api.get(f"/purchase-orders/{po['id']}")
    assert (saved["remark"], saved["lines"][0]["qty_planned"]) == ("colleague", 7)
