"""Outbound: sales order -> allocate -> pick -> ship, and the stock it consumes."""

from tests.helpers import Api, balance, make_item, make_warehouse, put_away, receive


def _stocked(api: Api, unique: str, qty: float):
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"OUT{unique}")
    receive(api, wh, item, qty)
    put_away(api, wh, item, qty)
    return wh, item


def test_order_to_shipment(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 10)

    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 7}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    allocation = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})
    assert balance(api, item, wh.bin) == (10, 7)

    pick_id = allocation["pick"]["id"]
    api.post(f"/picks/{pick_id}/confirm-all")
    api.post(f"/picks/{pick_id}/post")
    assert balance(api, item, wh.bin) == (3, 0)
    assert balance(api, item, wh.dock_out)[0] == 7

    shipment = api.post("/shipments", {"so_id": so["id"]})
    api.post(f"/shipments/{shipment['id']}/post")
    assert balance(api, item, wh.dock_out)[0] == 0
    assert api.get(f"/sales-orders/{so['id']}")["status"] == "SHIPPED"


def test_allocation_fails_without_stock(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"NS{unique}")
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})
    api.post(f"/sales-orders/{so['id']}/confirm")

    response = client.post(f"/api/v1/sales-orders/{so['id']}/allocate", headers=admin_headers,
                           json={"staging_location_id": wh.dock_out})
    assert response.status_code == 400, response.text


def test_partial_allocation_shows_in_shortage_report(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 2)
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})

    assert balance(api, item, wh.bin) == (2, 2)
    shortages = [row for row in api.get("/sales-orders/shortages") if row["so_id"] == so["id"]]
    assert len(shortages) == 1, "a partially allocated line must appear in the shortage report"
    assert float(shortages[0]["unallocated"]) == 3
