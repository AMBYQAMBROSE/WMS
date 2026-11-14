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


def test_balances_filter_for_nothing_available(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 2)

    def unavailable_locations() -> set[str]:
        return {r["location"]["id"] for r in api.get("/stock/balances", item_id=item, unavailable=True)}

    assert wh.bin not in unavailable_locations()
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 2}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})
    assert wh.bin in unavailable_locations(), "a fully allocated balance must match the filter"


def test_ledger_filter_by_movement_type(client, admin_headers, unique):
    api = Api(client, admin_headers)
    _, item = _stocked(api, unique, 3)
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=item, movement_type="RECEIVE")}
    assert types == {"RECEIVE"}


def _picked_order(api: Api, wh, item: str, qty: float) -> tuple[dict, str]:
    """A confirmed order for qty, picked in full to the staging dock; returns (order, pick id)"""
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick_id = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]["id"]
    api.post(f"/picks/{pick_id}/confirm-all")
    api.post(f"/picks/{pick_id}/post")
    return so, pick_id


def test_same_item_on_two_lines_is_not_reserved_twice(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 6)
    line = {"item_id": item, "uom_id": wh.ea, "qty": 5}
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [line, line]})
    api.post(f"/sales-orders/{so['id']}/confirm")

    allocation = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})
    assert sum(float(l["qty_planned"]) for l in allocation["pick"]["lines"]) == 6, "only the 6 in stock can be picked"
    assert [float(s["qty"]) for s in allocation["shortages"]] == [4]
    assert balance(api, item, wh.bin) == (6, 6)

    pick_id = allocation["pick"]["id"]
    api.post(f"/picks/{pick_id}/confirm-all")
    api.post(f"/picks/{pick_id}/post")
    assert balance(api, item, wh.bin) == (0, 0)


def test_staged_goods_are_reserved_until_shipped(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 5)
    so, _ = _picked_order(api, wh, item, 5)
    assert balance(api, item, wh.dock_out) == (5, 5), "goods in staging stay reserved for their order"

    move = api.post("/moves", {"lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 5, "from_location_id": wh.dock_out, "to_location_id": wh.bin,
    }]})
    response = client.post(f"/api/v1/moves/{move['id']}/post", headers=admin_headers)
    assert response.status_code == 400, "staged goods must not be moved away from under the order"
    assert "allocated to orders" in response.text

    shipment = api.post("/shipments", {"so_id": so["id"]})
    api.post(f"/shipments/{shipment['id']}/post")
    assert balance(api, item, wh.dock_out) == (0, 0)


def test_reverse_pick_returns_goods_and_frees_the_order(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 5)
    so, pick_id = _picked_order(api, wh, item, 5)
    for action in ("cancel", "close"):
        response = client.post(f"/api/v1/sales-orders/{so['id']}/{action}", headers=admin_headers)
        assert response.status_code == 400, f"{action} must be refused while goods are in staging"

    assert api.post(f"/picks/{pick_id}/reverse")["status"] == "REVERSED"
    assert balance(api, item, wh.bin) == (5, 0)
    assert balance(api, item, wh.dock_out) == (0, 0)
    line = api.get(f"/sales-orders/{so['id']}")["lines"][0]
    assert (float(line["picked"]), float(line["unallocated"])) == (0, 5)
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=item)}
    assert {"UNPICK_OUT", "UNPICK_IN"} <= types

    assert api.post(f"/sales-orders/{so['id']}/cancel")["status"] == "CANCELLED"


def test_reverse_pick_refused_once_shipped_or_loading(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh, item = _stocked(api, unique, 5)
    so, pick_id = _picked_order(api, wh, item, 3)

    shipment = api.post("/shipments", {"so_id": so["id"]})
    response = client.post(f"/api/v1/picks/{pick_id}/reverse", headers=admin_headers)
    assert response.status_code == 400 and "being loaded" in response.text

    api.post(f"/shipments/{shipment['id']}/post")
    response = client.post(f"/api/v1/picks/{pick_id}/reverse", headers=admin_headers)
    assert response.status_code == 400 and "already shipped" in response.text
    assert balance(api, item, wh.bin) == (2, 0)
