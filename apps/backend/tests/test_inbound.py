"""Inbound: purchase order -> goods receipt -> putaway, and the stock it produces."""

import uuid

from tests.helpers import Api, balance, make_item, make_warehouse, put_away, receive


def test_receive_and_put_away(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"IN{unique}")

    grn = receive(api, wh, item, 10)
    assert grn["status"] == "POSTED"
    assert balance(api, item, wh.dock_in) == (10, 0)

    put_away(api, wh, item, 4)
    assert balance(api, item, wh.dock_in) == (6, 0)
    assert balance(api, item, wh.bin) == (4, 0)

    ledger = api.get("/stock/ledger", item_id=item)
    assert sum(float(row["qty_change"]) for row in ledger) == 10


def test_putaway_cannot_move_more_than_on_hand(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"OV{unique}")
    receive(api, wh, item, 3)

    putaway = api.post("/putaways", {"lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 5,
        "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    response = client.post(f"/api/v1/putaways/{putaway['id']}/post", headers=admin_headers)
    assert response.status_code in (400, 409), response.text
    assert balance(api, item, wh.dock_in) == (3, 0)


def test_grn_submit_is_idempotent(client, admin_headers, unique):
    """The PDA resubmits with the same client_request_id after a timeout; it must not receive twice"""
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"ID{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")

    body = {
        "po_id": po["id"], "location_id": wh.dock_in, "client_request_id": str(uuid.uuid4()),
        "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 5}],
    }
    first = client.post("/api/v1/grns", json=body, headers=admin_headers)
    second = client.post("/api/v1/grns", json=body, headers=admin_headers)
    assert first.is_success and second.is_success, (first.text, second.text)
    assert first.json()["id"] == second.json()["id"]


def test_cancelled_po_cannot_be_received(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"CX{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5}]})
    api.post(f"/purchase-orders/{po['id']}/cancel")

    response = client.post("/api/v1/grns", headers=admin_headers, json={
        "po_id": po["id"], "location_id": wh.dock_in,
        "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 5}],
    })
    assert response.status_code in (400, 409), response.text
