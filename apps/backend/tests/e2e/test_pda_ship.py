"""PDA shipping: every piece is scanned onto the vehicle (a carton counts its pack size), then the delivery order posts;
and the home screen's scan field opens the right task."""

import uuid

from playwright.sync_api import Page, expect

from tests.e2e.flows.conftest import add_conversion, db_session
from tests.e2e.test_labels import shot
from tests.e2e.test_pda import pda_sign_in, scan
from tests.helpers import Api, make_item, make_warehouse, put_away, receive


def add_barcode(item_id: str, barcode: str, uom_id: str) -> None:
    """Carton barcode for an item (no API for item barcodes yet; written directly like add_conversion)"""
    from app.models.item import Item, ItemBarcode

    with db_session() as db:
        item = db.get(Item, uuid.UUID(item_id))
        db.add(ItemBarcode(tenant_id=item.tenant_id, item_id=item.id, barcode=barcode, uom_id=uuid.UUID(uom_id),
                           created_by=item.created_by, updated_by=item.created_by))
        db.commit()


def test_load_every_piece_then_post(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    ctn = next(u["id"] for u in api.get("/uoms") if u["code"] == "CTN")
    item = make_item(api, wh, f"SH{unique}")
    add_conversion(item, ctn, wh.ea, 12)
    add_barcode(item, f"CTN{unique}", ctn)
    receive(api, wh, item, 14)
    put_away(api, wh, item, 14)
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 14}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    vehicle = f"V{unique}"

    pda_sign_in(page, pda_url)
    # The home screen's scan field: the pick list number opens loading for its order
    scan(page, "scan-home", pick["doc_no"])
    expect(page.get_by_test_id("loaded-count")).to_contain_text("0", timeout=15_000)

    scan(page, "scan-piece", f"NOPE{unique}")
    expect(page.get_by_text(f"Unknown barcode NOPE{unique}")).to_be_visible()
    scan(page, "scan-piece", f"CTN{unique}")  # one carton = 12 pieces
    expect(page.get_by_test_id("loaded-count")).to_contain_text("12")
    scan(page, "scan-piece", f"CTN{unique}")  # only 2 left
    expect(page.get_by_text("Too many")).to_be_visible()
    for _ in range(2):
        scan(page, "scan-piece", f"SH{unique}")
    expect(page.get_by_test_id("loaded-count")).to_contain_text("14")

    page.get_by_test_id("vehicle-no").fill(vehicle)
    page.get_by_test_id("driver-name").fill("Driver")
    page.get_by_test_id("seal-no").fill(f"SEAL{unique}")
    shot(page, "pda-ship-loaded")
    page.get_by_test_id("post-delivery").click()
    expect(page.get_by_text("posted; print it in the web console")).to_be_visible(timeout=20_000)

    [ship] = api.get("/shipments", so_id=so["id"])
    ship = api.get(f"/shipments/{ship['id']}")
    assert ship["status"] == "POSTED"
    assert ship["lines"][0]["qty_checked"] == 14
    assert (ship["shipment_info"]["vehicle_no"], ship["shipment_info"]["seal_no"]) == (vehicle, f"SEAL{unique}")
    # Posted with everything scanned: nothing recorded as skipped
    logs = api.get("/audit-logs", entity_id=ship["id"])
    assert not [c for log in logs for c in log["changes"] if c["field"] == "posted_without_full_scan"]


def test_home_scan_shows_stock_of_a_bin(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"HS{unique}")
    receive(api, wh, item, 3)
    put_away(api, wh, item, 3)

    pda_sign_in(page, pda_url)  # downloads the new bin and item
    scan(page, "scan-home", f"BIN{unique}")
    expect(page.get_by_test_id("stock-subject")).to_have_text(f"BIN{unique}")
    expect(page.get_by_text(f"HS{unique}", exact=True)).to_be_visible()
    expect(page.get_by_text("3 EA")).to_be_visible()
