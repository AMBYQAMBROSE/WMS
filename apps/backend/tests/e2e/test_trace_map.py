"""Warehouse map, batch trace and recall in the browser."""

import os
import re
from datetime import date, timedelta

from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, Warehouse
from tests.test_trace_and_map import batch_item, receive_batch, staged

SHOTS = os.environ.get("E2E_SCREENSHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)


def floor(api: Api, unique: str) -> tuple[Warehouse, list[str], str]:
    """Warehouse > zone > aisle > two racks of bins, plus docks: (warehouse, bins, quarantine bin)"""
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    supplier = api.post("/business-partners", {"code": f"S{unique}", "name": "Fresh Foods Ltd", "partner_type": "supplier"})
    customer = api.post("/business-partners", {"code": f"C{unique}", "name": "Corner Store", "partner_type": "customer",
                                               "contact_name": "Sam", "contact_phone": "555-0100", "address": "1 High Street"})
    wh = api.post("/locations", {"code": f"W{unique}", "name": "Main warehouse", "location_type": "WAREHOUSE"})

    def loc(code: str, kind: str, parent: str, **extra) -> str:
        return api.post("/locations", {"code": f"{code}{unique}", "name": code, "location_type": kind, "parent_id": parent, **extra})["id"]

    dock_in, dock_out = loc("IN", "DOCK", wh["id"]), loc("OUT", "DOCK", wh["id"])
    zone = loc("Z1-", "ZONE", wh["id"])
    aisle = loc("A1-", "AISLE", zone)
    bins = []
    for r in (1, 2):
        rack = loc(f"R{r}-", "RACK", aisle)
        bins += [loc(f"B{r}{i}-", "BIN", rack, is_pickable=True, capacity_qty=20) for i in range(1, 7)]
    quarantine = loc("QA-", "BIN", zone)
    return Warehouse(warehouse=wh["id"], ea=ea, supplier=supplier["id"], customer=customer["id"],
                     dock_in=dock_in, bin=bins[0], dock_out=dock_out), bins, quarantine


def test_map_trace_and_recall(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, bins, quarantine = floor(api, unique)
    item = batch_item(api, wh, f"MILK{unique}")
    batch = f"L{unique}"
    receive_batch(api, wh, item, 12, batch, date.today() + timedelta(days=20))
    _, _, ship = staged(api, wh, item, 4)
    api.post(f"/shipments/{ship['id']}/post")

    sign_in(page)
    page.goto(f"/warehouse-map?warehouse={wh.warehouse}")
    board = page.get_by_test_id("warehouse-map")
    expect(board.get_by_role("button", name=re.compile(rf"Bin B11-{unique}: 8 on hand"))).to_be_visible()
    expect(board.get_by_text(f"Z1-{unique}")).to_be_visible()
    shot(page, "map-fill")
    for metric in ("Pick heat", "Expiry", "Status"):
        page.locator(".wms-map-card .ant-segmented").get_by_text(metric, exact=True).click()
    shot(page, "map-status")

    # Something happens while the map is open: the bin pulses
    _, pick, _ = staged(api, wh, item, 1)
    expect(board.locator(".wms-map-ping").first).to_be_attached(timeout=15_000)
    expect(page.get_by_text(re.compile(rf"picked MILK{unique}")).first).to_be_visible()

    board.get_by_role("button", name=re.compile(rf"Bin B11-{unique}")).click()
    drawer = page.get_by_role("dialog")
    expect(drawer.get_by_role("link", name=batch)).to_be_visible()
    shot(page, "map-drawer")
    drawer.get_by_role("link", name=batch).click()

    # The trace: supplier on the left, customer and stock on the right
    expect(page).to_have_url(re.compile(r"/trace\?item="))
    flow = page.get_by_test_id("trace-flow")
    expect(flow.get_by_text("Fresh Foods Ltd")).to_be_visible()
    expect(flow.get_by_text("Corner Store")).to_be_visible()
    expect(flow.locator("path").first).to_be_attached()
    shot(page, "trace")

    page.get_by_role("button", name="Recall this batch").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Reason").fill("Supplier reported a cold-chain break")
    dialog.get_by_role("combobox", name="Quarantine location").fill(f"QA-{unique}")
    page.get_by_title(re.compile(rf"QA-{unique}")).click()
    dialog.get_by_role("button", name="Start recall").click()

    expect(page).to_have_url(re.compile(r"/recalls/"))
    expect(page.get_by_text(f"Batch {batch} is on hold")).to_be_visible()
    expect(page.get_by_role("cell", name="Corner Store").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"Move\s+MV"))).to_be_visible()
    shot(page, "recall")

    # Reverse trace from the delivery order the customer complains about
    page.goto(f"/trace?doc={ship['doc_no']}")
    expect(page.get_by_role("link", name=batch)).to_be_visible()
    expect(page.get_by_text("On hold").first).to_be_visible()
    shot(page, "trace-document")

    page.goto(f"/warehouse-map?warehouse={wh.warehouse}")
    page.get_by_text("Replay a day").click()
    page.get_by_role("button", name="Play").click()
    # Every event of the day plays, and the feed follows it
    expect(page.get_by_text(re.compile(r"^([1-9]\d*) of \1 events$"))).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="Play")).to_be_visible()
    expect(page.get_by_text(re.compile(rf"picked MILK{unique}")).first).to_be_visible()
    shot(page, "map-replay")
    assert pick["id"]
    assert errors == []
