"""List pages: batch actions, saved views and column settings, in the browser."""

import time

from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_item, make_warehouse, receive


def _wait_saved(api: Api, key: str, check) -> dict:
    """Saves are optimistic: wait until the server has the setting before reloading"""
    deadline = time.time() + 10
    while True:
        value = api.get(f"/me/preferences/{key}")["value"]
        if value and check(value):
            return value
        assert time.time() < deadline, f"{key} not saved: {value}"
        time.sleep(0.2)


def _putaway(api: Api, wh, item: str, qty: float, remark: str) -> dict:
    return api.post("/putaways", {"remark": remark, "lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": qty, "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})


def test_batch_post_reports_each_document(page: Page, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"BT{unique}")
    receive(api, wh, item, 10)
    tag = f"batch-{unique}"
    ok = [_putaway(api, wh, item, 2, tag), _putaway(api, wh, item, 3, tag)]
    too_much = _putaway(api, wh, item, 50, tag)
    posted = _putaway(api, wh, item, 1, tag)
    api.post(f"/putaways/{posted['id']}/post")

    sign_in(page)
    page.goto("/putaways")
    page.get_by_placeholder("Search number, partner, remark…").fill(tag)
    expect(page.locator(".ant-table-tbody tr.ant-table-row")).to_have_count(4)
    page.locator(".ant-table-thead .ant-checkbox-input").check()
    page.get_by_role("button", name="Post (3)").click()
    page.get_by_role("button", name="OK").click()

    expect(page.get_by_test_id("batch-summary")).to_have_text("2 done · 1 skipped · 1 failed · of 4", timeout=15_000)
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text(too_much["doc_no"])).to_be_visible()
    expect(dialog.get_by_text("Status is POSTED")).to_be_visible()
    for doc in ok:
        assert api.get(f"/putaways/{doc['id']}")["status"] == "POSTED"
    assert api.get(f"/putaways/{too_much['id']}")["status"] == "DRAFT"


def test_default_view_is_applied_on_open(page: Page, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    api.post("/purchase-orders", {"partner_id": wh.supplier, "remark": f"view-{unique}",
                                  "lines": [{"item_id": make_item(api, wh, f"VW{unique}"), "uom_id": wh.ea, "qty": 1}]})

    sign_in(page)
    page.goto("/purchase-orders")
    page.get_by_role("button", name="Draft", exact=True).click()
    page.get_by_placeholder("Search number, partner, remark…").fill(f"view-{unique}")
    expect(page.locator(".ant-table-tbody tr.ant-table-row")).to_have_count(1)

    page.get_by_role("button", name="Views").click()
    page.get_by_text("Save current filters as a view…").click()
    page.get_by_placeholder("e.g. Drafts this week").fill(f"Mine {unique}")
    page.get_by_role("button", name="Save").click()
    page.get_by_role("button", name=f"Mine {unique}").click()
    page.get_by_role("button", name=f"Open Mine {unique} by default").click()
    page.keyboard.press("Escape")
    saved = _wait_saved(api, "list:purchase-orders", lambda v: v.get("defaultView") == f"Mine {unique}")

    page.reload()
    expect(page.get_by_placeholder("Search number, partner, remark…")).to_have_value(f"view-{unique}")
    expect(page.locator(".ant-table-tbody tr.ant-table-row")).to_have_count(1)
    expect(page.get_by_role("button", name=f"Mine {unique}")).to_be_visible()

    # Stored on the server for this user, not in the browser
    assert next(v for v in saved["views"] if v["name"] == f"Mine {unique}")["filters"]["status"] == "DRAFT"
    api.call("PUT", "/me/preferences/list:purchase-orders", {"value": {"views": [], "hidden": []}})  # leave no default behind


def test_hidden_column_stays_hidden(page: Page, client, admin_headers):
    sign_in(page)
    page.goto("/sales-orders")
    header = page.locator(".ant-table-thead").get_by_text("Remark", exact=True)
    expect(header).to_be_visible()
    page.get_by_role("button", name="Choose columns").click()
    page.get_by_role("checkbox", name="Remark").uncheck()
    expect(header).to_have_count(0)
    _wait_saved(Api(client, admin_headers), "list:sales-orders", lambda v: "Remark" in v["hidden"])

    page.reload()
    expect(page.locator(".ant-table-thead").get_by_text("Customer", exact=True)).to_be_visible()
    expect(header).to_have_count(0)
    Api(client, admin_headers).call("PUT", "/me/preferences/list:sales-orders", {"value": {"views": [], "hidden": []}})
