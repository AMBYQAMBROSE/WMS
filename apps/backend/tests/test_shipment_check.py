"""Loading check: every piece of a shipment is scanned before it is posted; the PDA's lookup and loading history."""

from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse, put_away, receive


def staged_shipment(api: Api, unique: str, qty: int = 5) -> tuple[dict, dict, dict]:
    """Order picked to staging and a draft shipment for it: (shipment, sales order, pick list)"""
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"SC{unique}")
    receive(api, wh, item, qty)
    put_away(api, wh, item, qty)
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    ship = api.post("/shipments", {"so_id": so["id"], "vehicle_no": f"V{unique}", "driver_name": "Driver", "carrier": f"Carrier {unique}"})
    return ship, so, pick


def loader(client, admin: Api, unique: str) -> Api:
    """A warehouse user who may post shipments, but not without scanning every piece"""
    role = admin.post("/roles", {"code": f"LD{unique}", "name": "Loader", "permission_codes": [
        "shipment.read", "shipment.create", "shipment.post", "mobile.sync", "pick.read", "sales_order.read"]})
    admin.post("/users", {"username": f"ld{unique}", "display_name": "Loader", "password": "Load@Test123", "role_codes": [role["code"]]})
    return Api(client, login(client, f"ld{unique}", "Load@Test123"))


def test_shipment_posts_only_when_every_piece_is_scanned(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    ship, so, _ = staged_shipment(admin, unique)
    user = loader(client, admin, unique)
    [line] = ship["lines"]
    assert line["qty_checked"] == 0
    check = f"/shipments/{ship['id']}/lines/{line['id']}/check"

    user.post(check, {"qty": 3})
    user.post(check, {"qty": 3})  # a resend sets the same value again
    assert user.get(f"/shipments/{ship['id']}")["lines"][0]["qty_checked"] == 3
    response = user.call("POST", f"/shipments/{ship['id']}/post", expect=400)
    assert "3 of 5" in str(response)

    user.post(check, {"qty": 6}, expect=400)  # more than is on the shipment
    user.post(check, {"qty": 5})
    assert user.post(f"/shipments/{ship['id']}/post")["status"] == "POSTED"
    assert admin.get(f"/sales-orders/{so['id']}")["status"] == "SHIPPED"


def test_supervisor_may_post_without_scanning_and_it_is_recorded(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    ship, _, _ = staged_shipment(admin, unique)
    assert admin.post(f"/shipments/{ship['id']}/post")["status"] == "POSTED"
    logs = admin.get("/audit-logs", entity_id=ship["id"])
    recorded = [c for log in logs for c in log["changes"] if c["field"] == "posted_without_full_scan"]
    assert recorded and "0 of 5" in recorded[0]["new"]


def test_lookup_and_loading_history_for_the_pda(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    ship, so, pick = staged_shipment(admin, unique)
    user = loader(client, admin, unique)

    [hit] = user.get("/mobile/lookup", code=pick["doc_no"])
    assert (hit["doc_type"], hit["id"], hit["ref_document_id"]) == ("PICK", pick["id"], so["id"])
    assert user.get("/mobile/lookup", code=f"NOPE{unique}") == []
    # Documents the user may not read are not found
    grn = admin.get("/grns", limit=1)[0]
    assert user.get("/mobile/lookup", code=grn["doc_no"]) == []

    history = user.get("/shipments/loading-history")
    assert f"Carrier {unique}" in history["carriers"]
    vehicle = next(v for v in history["vehicles"] if v["vehicle_no"] == f"V{unique}")
    assert (vehicle["driver_name"], vehicle["seal_no"]) == ("Driver", None)
    assert ship["shipment_info"]["vehicle_no"] == f"V{unique}"
