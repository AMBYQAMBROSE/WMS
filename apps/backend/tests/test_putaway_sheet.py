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
    assert line["to_location"]["id"] in (wh.bin, bin2), "one pallet, into an empty bin of the warehouse"

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


def test_a_bin_holds_one_pallet_so_occupied_bins_are_skipped(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bin2 = api.post("/locations", {"code": f"BIN2{unique}", "name": "Bin 2", "location_type": "BIN", "parent_id": wh.warehouse})["id"]
    item = make_item(api, wh, f"SG{unique}")
    first = sheet_for(api, receive(api, wh, item, 5)["id"])
    api.post(f"/putaways/{first['id']}/cancel")
    put_away(api, wh, item, 5)

    # BIN holds stock (even of the same item), so the next pallet goes to the empty bin
    sheet = sheet_for(api, receive(api, wh, item, 3)["id"])
    assert sheet["lines"][0]["to_location"]["id"] == bin2
    assert pages(print_doc(client, admin_headers, sheet["id"])) == 1

    # BIN2 now has a pallet on its way: no bin is free, so the operator chooses one
    sheet = sheet_for(api, receive(api, wh, item, 2)["id"])
    assert sheet["lines"][0]["to_location"] is None


def test_receipt_over_a_pallet_goes_to_one_empty_bin_per_pallet(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bins = [wh.bin] + [
        api.post("/locations", {"code": f"B{n}{unique}", "name": f"Bin {n}", "location_type": "BIN", "parent_id": wh.warehouse})["id"]
        for n in range(2, 7)
    ]
    plt = next(u["id"] for u in api.get("/uoms") if u["code"] == "PLT")
    packed = api.post("/items", {"sku_code": f"PP{unique}", "name": "Packed", "base_uom_id": wh.ea,
                                 "packings": [{"uom_id": plt, "factor": 100}]})["id"]
    plain = make_item(api, wh, f"PD{unique}", pallet_qty=500)

    # Each item's own pallet quantity: 100 and 500
    lines = sheet_for(api, receive(api, wh, packed, 250)["id"])["lines"] + sheet_for(api, receive(api, wh, plain, 1200)["id"])["lines"]
    assert [(line["item"]["id"], line["qty_planned"]) for line in lines] == [
        (packed, 100), (packed, 100), (packed, 50), (plain, 500), (plain, 500), (plain, 200),
    ]
    targets = [line["to_location"]["id"] for line in lines]
    assert sorted(targets) == sorted(bins), "every pallet in its own bin"

    # A pallet of exactly the pallet size stays one line
    item = make_item(api, wh, f"PE{unique}", pallet_qty=500)
    api.post("/locations", {"code": f"B7{unique}", "name": "Bin 7", "location_type": "BIN", "parent_id": wh.warehouse})
    assert [line["qty_planned"] for line in sheet_for(api, receive(api, wh, item, 500)["id"])["lines"]] == [500]


def test_receipts_posted_at_the_same_time_never_share_a_bin(client, admin_headers, unique):
    """A receipt still posting holds row locks on the bins it claimed: another receipt skips them, without waiting"""
    import threading
    import uuid

    from app.core.db import SessionLocal
    from app.models.location import Location
    from app.services.transfer_service import PutawayService

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bin2 = api.post("/locations", {"code": f"BIN2{unique}", "name": "Bin 2", "location_type": "BIN", "parent_id": wh.warehouse})["id"]
    item = make_item(api, wh, f"LK{unique}")

    with SessionLocal() as other:
        dock = other.get(Location, uuid.UUID(wh.dock_in))
        [held] = PutawayService(other, dock.tenant_id, dock.created_by)._claim_bins(dock, 1)
        result: dict = {}
        posting = threading.Thread(target=lambda: result.update(grn=receive(api, wh, item, 3)))
        try:
            posting.start()
            posting.join(30)
            assert not posting.is_alive(), "the receipt must skip the locked bin, not wait for it"
        finally:
            other.rollback()
            posting.join(30)

    [line] = sheet_for(api, result["grn"]["id"])["lines"]
    expected = ({wh.bin, bin2} - {str(held)}).pop()
    assert line["to_location"]["id"] == expected


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


def test_putaway_remaining_of_a_receipt(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"RM{unique}")
    grn = receive(api, wh, item, 10)

    def remaining() -> list[float]:
        return [float(r["qty"]) for r in api.get(f"/grns/{grn['id']}/putaway-remaining")]

    assert remaining() == [10], "an untouched putaway sheet covers nothing yet"
    putaway = api.post("/putaways", {"ref_document_id": grn["id"], "lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 4, "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    assert remaining() == [6], "a drafted putaway already covers its quantity"
    api.post(f"/putaways/{putaway['id']}/post")
    assert remaining() == [6]

    rest = api.post("/putaways", {"ref_document_id": grn["id"], "lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 6, "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    assert remaining() == [0]
    api.post(f"/putaways/{rest['id']}/cancel")
    assert remaining() == [6], "a cancelled putaway covers nothing"
