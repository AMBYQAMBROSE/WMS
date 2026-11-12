"""Putaway sheets: made when a receipt is posted into a dock, worked line by line, posted when everything is put away."""

from tests.helpers import PREFIX, Api, balance, make_item, make_warehouse, put_away, receive
from tests.test_document_print import print_doc
from tests.test_labels import pages


def sheet_for(api: Api, grn_id: str) -> dict:
    sheets = api.get("/putaways", ref_document_id=grn_id)
    assert len(sheets) == 1, sheets
    return api.get(f"/putaways/{sheets[0]['id']}")


def test_receipt_into_dock_makes_a_sheet_put_away_in_two_bins(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bin2 = api.post("/locations", {"code": f"BIN2{unique}", "name": "Bin 2", "location_type": "BIN", "parent_id": wh.warehouse})["id"]
    item = make_item(api, wh, f"PS{unique}")
    grn = receive(api, wh, item, 10)

    sheet = sheet_for(api, grn["id"])
    assert sheet["status"] == "TO_PUT_AWAY"
    assert sheet["location"]["id"] == wh.dock_in
    [line] = sheet["lines"]
    assert (line["qty_planned"], line["qty_actual"], line["confirmed_at"]) == (10, 0, None)
    assert line["to_location"] is None, "first receipt of the item: no bin to suggest"

    # The bin is full after 6: the rest splits off as a new open line
    sheet = api.post(f"/putaways/{sheet['id']}/lines/{line['id']}/put", {"to_location_id": wh.bin, "qty": 6})
    done, rest = sheet["lines"]
    assert (done["qty_actual"], done["to_location"]["id"], done["confirmed_at"] is not None) == (6, wh.bin, True)
    assert (rest["qty_planned"], rest["confirmed_at"]) == (4, None)
    api.post(f"/putaways/{sheet['id']}/post", expect=400)

    # A PDA that worked offline still knows only the first line: its put goes to the open rest
    sheet = api.post(f"/putaways/{sheet['id']}/lines/{line['id']}/put", {"to_location_id": bin2, "qty": 4})
    assert all(entry["confirmed_at"] for entry in sheet["lines"])
    api.post(f"/putaways/{sheet['id']}/lines/{line['id']}/put", {"to_location_id": bin2, "qty": 1}, expect=400)

    assert api.post(f"/putaways/{sheet['id']}/post")["status"] == "POSTED"
    assert balance(api, item, wh.dock_in)[0] == 0
    assert balance(api, item, wh.bin)[0] == 6
    assert balance(api, item, bin2)[0] == 4
    assert pages(print_doc(client, admin_headers, sheet["id"])) == 1


def test_next_receipt_suggests_the_bin_holding_the_item(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"SG{unique}")
    receive(api, wh, item, 5)
    put_away(api, wh, item, 5)

    grn = receive(api, wh, item, 3)
    sheet = sheet_for(api, grn["id"])
    assert sheet["lines"][0]["to_location"]["id"] == wh.bin
    assert pages(print_doc(client, admin_headers, sheet["id"])) == 1


def test_put_checks_quantity_target_and_resend(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"PC{unique}")
    sheet = sheet_for(api, receive(api, wh, item, 5)["id"])
    line = sheet["lines"][0]
    put = f"/putaways/{sheet['id']}/lines/{line['id']}/put"

    api.post(put, {"to_location_id": wh.bin, "qty": 6}, expect=400)
    api.post(put, {"to_location_id": wh.dock_out, "qty": 5}, expect=400)  # bins only

    # A resend with the same Idempotency-Key (lost response) is answered from the first put, not applied twice
    headers = {**admin_headers, "Idempotency-Key": f"put-{unique}"}
    for _ in range(2):
        response = client.post(PREFIX + put, json={"to_location_id": wh.bin, "qty": 2}, headers=headers)
        assert response.status_code == 200, response.text
    lines = api.get(f"/putaways/{sheet['id']}")["lines"]
    assert sorted((entry["qty_planned"], entry["confirmed_at"] is not None) for entry in lines) == [(2, True), (3, False)]

    assert api.post(f"/putaways/{sheet['id']}/cancel")["status"] == "CANCELLED"


def test_putaway_by_hand_replaces_an_untouched_sheet(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"RP{unique}")
    grn = receive(api, wh, item, 4)
    sheet = sheet_for(api, grn["id"])
    body = {"ref_document_id": grn["id"], "lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 2, "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]}

    # Once something on the sheet is put away, a second plan for the same receipt is refused
    api.post(f"/putaways/{sheet['id']}/lines/{sheet['lines'][0]['id']}/put", {"to_location_id": wh.bin, "qty": 2})
    api.post("/putaways", body, expect=400)

    grn2 = receive(api, wh, item, 3)
    sheet2 = sheet_for(api, grn2["id"])
    api.post("/putaways", {**body, "ref_document_id": grn2["id"]})
    assert api.get(f"/putaways/{sheet2['id']}")["status"] == "CANCELLED"


def test_receipt_straight_into_a_bin_needs_no_sheet(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"NB{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 2}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.bin, "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 2}]})
    api.post(f"/grns/{grn['id']}/post")
    assert api.get("/putaways", ref_document_id=grn["id"]) == []
