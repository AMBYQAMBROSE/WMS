"""Warehouse map (live bins, activity), batch traceability (forward and reverse) and batch recalls."""

from datetime import UTC, date, datetime, timedelta

from tests.conftest import login
from tests.helpers import Api, Warehouse, make_warehouse, pallet


def batch_item(api: Api, wh: Warehouse, sku: str) -> str:
    return api.post("/items", {
        "sku_code": sku, "name": f"Item {sku}", "base_uom_id": wh.ea, "packings": pallet(api), "is_batch_managed": True, "is_expiry_managed": True,
    })["id"]


def receive_batch(api: Api, wh: Warehouse, item: str, qty: float, batch: str, expiry: date) -> tuple[dict, dict]:
    """PO -> GRN with a batch -> post -> put away into the bin; (purchase order, receipt)"""
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": [
        {"po_line_id": po["lines"][0]["id"], "qty": qty, "batch_no": batch, "expiry_date": expiry.isoformat()}]})
    grn = api.post(f"/grns/{grn['id']}/post")
    # Posting a receipt into a dock makes a putaway sheet; a free putaway moves the goods into the bin just as well
    for sheet in api.get("/putaways", ref_document_id=grn["id"]):
        api.post(f"/putaways/{sheet['id']}/cancel")
    putaway = api.post("/putaways", {"lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": qty, "batch_no": batch, "expiry_date": expiry.isoformat(),
        "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    api.post(f"/putaways/{putaway['id']}/post")
    return po, grn


def staged(api: Api, wh: Warehouse, item: str, qty: float) -> tuple[dict, dict, dict]:
    """Order allocated, picked to staging, with a draft shipment: (order, pick, shipment)"""
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    ship = api.post("/shipments", {"so_id": so["id"], "vehicle_no": "TRUCK-1", "driver_name": "Driver"})
    return so, pick, ship


def test_warehouse_map_shows_stock_picks_and_activity(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = batch_item(api, wh, f"MP{unique}")
    expiry = date.today() + timedelta(days=200)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5)
    receive_batch(api, wh, item, 10, f"B{unique}", expiry)
    so, pick, ship = staged(api, wh, item, 4)

    data = api.get("/stock/map", warehouse_id=wh.warehouse)
    assert data["warehouse"]["id"] == wh.warehouse
    nodes = {n["id"]: n for n in data["nodes"]}
    root = nodes[wh.warehouse]
    assert root["parent_id"] is None and root["location_type"] == "WAREHOUSE"
    bin_ = nodes[wh.bin]
    assert bin_["parent_id"] == wh.warehouse
    assert (bin_["qty_on_hand"], bin_["sku_count"], bin_["picks"]) == (6, 1, 1)
    assert bin_["nearest_expiry"] == expiry.isoformat()
    staging = nodes[wh.dock_out]
    assert (staging["qty_on_hand"], staging["qty_allocated"]) == (4, 4)

    activity = api.get("/stock/map/activity", warehouse_id=wh.warehouse, since=since.isoformat())
    kinds = {(e["kind"], e["movement_type"] or e["doc_type"], e["location_id"]) for e in activity["events"]}
    assert ("MOVEMENT", "RECEIVE", wh.dock_in) in kinds
    assert ("MOVEMENT", "PUTAWAY_IN", wh.bin) in kinds
    assert ("MOVEMENT", "PICK_OUT", wh.bin) in kinds
    # The PDA confirmation shows at the bin it was picked from, by the user who did it
    scan = next(e for e in activity["events"] if e["kind"] == "SCAN" and e["doc_type"] == "PICK")
    assert scan["location_id"] == wh.bin and scan["user_name"]
    times = [e["at"] for e in activity["events"]]
    assert times == sorted(times)

    detail = api.get(f"/stock/map/locations/{wh.bin}")
    assert detail["stock"][0]["batch_no"] == f"B{unique}" and detail["stock"][0]["qty_on_hand"] == 6
    assert detail["recent"] and detail["recent"][0]["at"] >= detail["recent"][-1]["at"]

    api.call("GET", "/stock/map/activity", expect=400, since="2026-01-01T00:00:00", until="2026-01-05T00:00:00")


def test_batch_trace_forward_and_reverse(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = batch_item(api, wh, f"TR{unique}")
    batch = f"LOT{unique}"
    po, grn = receive_batch(api, wh, item, 10, batch, date.today() + timedelta(days=100))
    so, _, ship = staged(api, wh, item, 4)
    api.post(f"/shipments/{ship['id']}/post")

    [hit] = api.get("/trace/batches", q=f"LOT{unique}")
    assert (hit["item"]["id"], hit["batch_no"], hit["qty_on_hand"], hit["recalled"]) == (item, batch, 6, False)

    trace = api.get("/trace/batch", item_id=item, batch_no=batch)
    s = trace["summary"]
    assert (s["received"], s["shipped"], s["qty_on_hand"], s["customers"], s["suppliers"]) == (10, 4, 6, 1, 1)
    [inbound] = trace["inbound"]
    assert inbound["document"]["id"] == grn["id"] and inbound["source"]["id"] == po["id"]
    assert inbound["partner"]["id"] == wh.supplier
    [outbound] = trace["outbound"]
    assert outbound["document"]["id"] == ship["id"] and outbound["source"]["id"] == so["id"]
    assert (outbound["partner"]["id"], outbound["qty"], outbound["vehicle_no"]) == (wh.customer, 4, "TRUCK-1")
    assert [(st["location"]["id"], st["qty_on_hand"]) for st in trace["stock"]] == [(wh.bin, 6)]
    assert trace["movements_total"] == len(trace["movements"]) and trace["active_recall"] is None

    # A customer complains about the delivery order: back to the batch, its supplier and receipt
    found = api.get("/trace/documents/lookup", doc_no=ship["doc_no"])
    assert found["document"]["id"] == ship["id"]
    [line] = found["batches"]
    assert (line["batch_no"], line["qty"], line["qty_on_hand"]) == (batch, 4, 6)
    assert [p["id"] for p in line["suppliers"]] == [wh.supplier]
    assert [r["id"] for r in line["receipts"]] == [grn["id"]]

    api.call("GET", "/trace/batch", expect=404, item_id=item, batch_no=f"NOPE{unique}")
    api.call("GET", "/trace/documents/lookup", expect=404, doc_no=f"NOPE{unique}")


def test_recall_holds_the_batch_and_drafts_a_quarantine_move(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    quarantine = api.post("/locations", {"code": f"QA{unique}", "name": "Quarantine", "location_type": "BIN",
                                         "parent_id": wh.warehouse})["id"]
    item = batch_item(api, wh, f"RC{unique}")
    bad, good = f"BAD{unique}", f"OK{unique}"
    receive_batch(api, wh, item, 10, bad, date.today() + timedelta(days=50))
    shipped_so, _, shipped = staged(api, wh, item, 2)
    api.post(f"/shipments/{shipped['id']}/post")
    # Picked and loaded but not yet gone when the recall starts
    _, _, waiting = staged(api, wh, item, 3)

    recall = api.post("/recalls", {"item_id": item, "batch_no": bad, "reason": "Supplier reported contamination",
                                   "quarantine_location_id": quarantine})
    doc = recall["document"]
    assert (doc["doc_type"], doc["status"], doc["location"]["id"]) == ("RECALL", "ACTIVE", quarantine)
    assert (doc["lines"][0]["qty_planned"], doc["lines"][0]["qty_actual"]) == (8, 2)
    [move] = recall["moves"]
    move = api.get(f"/moves/{move['id']}")
    assert move["status"] == "DRAFT" and move["ref_document"]["id"] == doc["id"]
    assert [(m["from_location"]["id"], m["to_location"]["id"], m["qty_actual"]) for m in move["lines"]] == [(wh.bin, quarantine, 5)]
    # The staged goods could not be moved; the recall says so
    assert [(s["location"]["id"], s["qty"]) for s in recall["skipped"]] == [(wh.dock_out, 3)]
    assert recall["trace"]["active_recall"]["id"] == doc["id"]
    assert [p["document"]["id"] for p in recall["trace"]["pending_shipments"]] == [waiting["id"]]

    api.post("/recalls", {"item_id": item, "batch_no": bad, "reason": "again"}, expect=409)

    # Held: the loaded shipment cannot leave, and new orders get no stock of the batch
    response = api.call("POST", f"/shipments/{waiting['id']}/post", expect=400)
    assert "recall" in str(response)
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    api.call("POST", f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out}, expect=400)
    # Other batches of the item are not held
    receive_batch(api, wh, item, 5, good, date.today() + timedelta(days=90))
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    assert {line["batch_no"] for line in pick["lines"]} == {good}

    api.post(f"/moves/{move['id']}/post")
    on_map = {n["id"]: n for n in api.get("/stock/map", warehouse_id=wh.warehouse)["nodes"]}
    assert on_map[quarantine]["has_recalled"] and on_map[quarantine]["qty_on_hand"] == 5

    response = client.get(f"/api/v1/recalls/{doc['id']}/customers.csv", headers=admin_headers)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = response.text.lstrip("﻿").strip().split("\r\n")
    assert len(rows) == 2 and shipped["doc_no"] in rows[1] and f"C{unique}" in rows[1]
    assert shipped_so["doc_no"] in rows[1]

    released = api.post(f"/recalls/{doc['id']}/release")
    assert released["document"]["status"] == "RELEASED" and released["trace"]["active_recall"] is None
    assert api.post(f"/shipments/{waiting['id']}/post")["status"] == "POSTED"
    assert any(r["id"] == doc["id"] for r in api.get("/recalls", status="RELEASED"))


def test_recall_permissions_and_typos(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    item = batch_item(admin, wh, f"RP{unique}")
    admin.post("/recalls", {"item_id": item, "batch_no": f"NEVER{unique}", "reason": "typo"}, expect=404)

    role = admin.post("/roles", {"code": f"RV{unique}", "name": "Viewer", "permission_codes": ["stock.read", "recall.read"]})
    admin.post("/users", {"username": f"rv{unique}", "display_name": "Viewer", "password": "View@Test123", "role_codes": [role["code"]]})
    viewer = Api(client, login(client, f"rv{unique}", "View@Test123"))
    viewer.post("/recalls", {"item_id": item, "batch_no": "X", "reason": "no"}, expect=403)
    assert isinstance(viewer.get("/recalls"), list)
    # Reverse trace only finds documents the user may read
    _, grn = receive_batch(admin, wh, item, 1, f"P{unique}", date.today() + timedelta(days=10))
    viewer.call("GET", "/trace/documents/lookup", expect=404, doc_no=grn["doc_no"])


def test_recall_prints_as_a_notice(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = batch_item(api, wh, f"PR{unique}")
    receive_batch(api, wh, item, 3, f"N{unique}", date.today() + timedelta(days=30))
    recall = api.post("/recalls", {"item_id": item, "batch_no": f"N{unique}", "reason": "Label misprint"})["document"]
    assert recall["location"] is None and recall["lines"][0]["qty_planned"] == 3
    response = client.get(f"/api/v1/documents/{recall['id']}/print", headers=admin_headers)
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
