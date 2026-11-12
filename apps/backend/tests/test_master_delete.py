"""Deleting master data: allowed when unused, refused while stock, child locations or open documents still use the record."""

from tests.helpers import Api, make_item, make_warehouse, put_away, receive


def test_unused_master_data_can_be_deleted(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"D{unique}")
    api.call("DELETE", f"/items/{item}", expect=204)
    assert api.get("/items", keyword=f"D{unique}") == []
    api.call("GET", f"/items/{item}", expect=404)

    api.call("DELETE", f"/locations/{wh.dock_out}", expect=204)
    api.call("DELETE", f"/business-partners/{wh.customer}", expect=204)
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
    assert "still has stock" in api.call("DELETE", f"/items/{item}", expect=409)["detail"]
    assert "still holds stock" in api.call("DELETE", f"/locations/{wh.bin}", expect=409)["detail"]


def test_records_on_open_documents_cannot_be_deleted(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"O{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 3}]})
    assert po["doc_no"] in api.call("DELETE", f"/items/{item}", expect=409)["detail"]
    assert po["doc_no"] in api.call("DELETE", f"/business-partners/{wh.supplier}", expect=409)["detail"]

    # Once the document is finished, the records may go
    api.post(f"/purchase-orders/{po['id']}/cancel")
    api.call("DELETE", f"/items/{item}", expect=204)
    api.call("DELETE", f"/business-partners/{wh.supplier}", expect=204)
