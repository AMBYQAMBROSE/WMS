"""Entry forms fill a line from the stock that is there: choosing a location brings its item (and free quantity),
and "Create and post" finishes the document in one click."""

import re

from playwright.sync_api import Locator, Page, expect

from tests.e2e.test_labels import shot
from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, balance, make_item, make_warehouse, put_away, receive


def choose(page: Page, select: Locator, text: str, option: str | None = None) -> None:
    """Type into a dropdown and click the match (`option`: its label, when the typed text matches several)"""
    select.click()
    page.keyboard.type(text, delay=20)
    page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option", has_text=option or text).first.click()


def test_location_fills_the_line_and_create_and_post(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    sku = f"AUTO{unique}"
    item = make_item(api, wh, sku)
    receive(api, wh, item, 9)
    put_away(api, wh, item, 4)  # 5 stay on the receiving dock, 4 are in the bin

    sign_in(page)

    # Putaway: the from location brings the only item on the dock and its free quantity
    page.goto("/putaways/new")
    row = page.locator(".ant-table-row").first
    selects = row.locator(".ant-select")
    # "IN…" is also found inside "BIN…": take the dock by its whole label
    choose(page, selects.nth(2), f"IN{unique}", f"IN{unique} IN")
    expect(row.get_by_text(f"{sku} Item {sku}")).to_be_visible()
    expect(row.get_by_role("spinbutton")).to_have_value("5")
    shot(page, "autofill-putaway")
    choose(page, selects.nth(3), f"BIN{unique}")
    page.get_by_test_id("create-and-post").click()
    expect(page.get_by_text("POSTED").or_(page.get_by_text("Posted", exact=True)).first).to_be_visible()
    assert balance(api, item, wh.dock_in)[0] == 0
    assert balance(api, item, wh.bin)[0] == 9

    # Adjustment: the location brings the item; the quantity is the user's to enter
    page.goto("/adjustments/new")
    reason = api.get("/reason-codes", category="ADJUST", active_only=True)[0]
    choose(page, page.get_by_label("Adjustment reason"), reason["code"])
    row = page.locator(".ant-table-row").first
    choose(page, row.locator(".ant-select").first, f"BIN{unique}")
    expect(row.get_by_text(f"{sku} Item {sku}")).to_be_visible()
    expect(row.get_by_role("spinbutton")).to_have_value("")
    row.get_by_role("spinbutton").fill("2")
    page.get_by_test_id("create-and-post").click()
    expect(page).to_have_url(re.compile(r"/adjustments/[0-9a-f-]{36}$"))
    assert balance(api, item, wh.bin)[0] == 7
    assert not errors
