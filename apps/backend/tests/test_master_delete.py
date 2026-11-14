"""Deleting master data removes the row from the database; it is refused while stock, child locations or documents use the record."""

from tests.helpers import Api, make_item, make_warehouse, put_away, receive


def test_unused_master_data_is_removed_and_its_code_can_be_reused(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"D{unique}")
    api.call("DELETE", f"/items/{item}", expect=204)
    assert api.get("/items", keyword=f"D{unique}") == []
    api.call("GET", f"/items/{item}", expect=404)
    # The row is gone, not flagged, so the unique code is free again
    make_item(api, wh, f"D{unique}")

    api.call("DELETE", f"/locations/{wh.dock_out}", expect=204)
    api.post("/locations", {"code": f"OUT{unique}", "name": "Again", "location_type": "DOCK", "parent_id": wh.warehouse})
    api.call("DELETE", f"/business-partners/{wh.customer}", expect=204)
    api.post("/business-partners", {"code": f"C{unique}", "name": "Again", "partner_type": "customer"})
    reason = api.post("/reason-codes", {"category": "ADJUST", "code": f"R{unique}", "name": "Reason"})
    api.call("DELETE", f"/reason-codes/{reason['id']}", expect=204)
    assert all(r["id"] != reason["id"] for r in api.get("/reason-codes"))


def test_location_with_children_cannot_be_deleted(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    response = api.call("DELETE", f"/locations/{wh.warehouse}", expect=409)
    assert "contains other locations" in response["detail"]


def test_records_with_stock_cannot_be_deleted(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"S{unique}")
    receive(api, wh, item, 5)
    put_away(api, wh, item, 5)
    assert "stock" in api.call("DELETE", f"/items/{item}", expect=409)["detail"]
    assert "stock" in api.call("DELETE", f"/locations/{wh.bin}", expect=409)["detail"]


def test_records_on_documents_cannot_be_deleted_even_when_finished(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"O{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 3}]})
    assert po["doc_no"] in api.call("DELETE", f"/items/{item}", expect=409)["detail"]
    assert po["doc_no"] in api.call("DELETE", f"/business-partners/{wh.supplier}", expect=409)["detail"]

    # A cancelled document still points at them, so they stay (and can be set inactive)
    api.post(f"/purchase-orders/{po['id']}/cancel")
    api.call("DELETE", f"/items/{item}", expect=409)
    api.call("DELETE", f"/business-partners/{wh.supplier}", expect=409)
