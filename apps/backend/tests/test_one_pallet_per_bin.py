"""A bin holds one pallet: one item, at most its pallet quantity. Checked on putaways and moves (drafted, posted, or
put away on the PDA); every item therefore needs its pallet quantity, also when imported."""

from tests.helpers import Api, make_item, make_warehouse, receive
from tests.test_order_import_and_cart import _import


def _bin(api: Api, wh, code: str) -> str:
    return api.post("/locations", {"code": code, "name": code, "location_type": "BIN", "parent_id": wh.warehouse})["id"]


def _putaway(api: Api, wh, item: str, qty: float, to: str, expect: int | None = None) -> dict:
    body = {"lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty, "from_location_id": wh.dock_in, "to_location_id": to}]}
    return api.post("/putaways", body, expect=expect)


def test_putaway_by_hand_keeps_one_pallet_of_one_item_per_bin(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"OP{unique}", pallet_qty=100)
    other = make_item(api, wh, f"OQ{unique}", pallet_qty=100)
    for sku in (item, other):
        api.post(f"/putaways/{api.get('/putaways', ref_document_id=receive(api, wh, sku, 300)['id'])[0]['id']}/cancel")

    # More than a pallet into one bin is refused; a pallet's worth is fine
    assert "more than one pallet (100 EA)" in _putaway(api, wh, item, 150, wh.bin, expect=400)["detail"]
    first = _putaway(api, wh, item, 60, wh.bin)

    # The bin is spoken for while that putaway is open: another item cannot go there, and the same item only up to a pallet
    assert "one pallet of one item" in _putaway(api, wh, other, 1, wh.bin, expect=400)["detail"]
    _putaway(api, wh, item, 41, wh.bin, expect=400)
    api.post(f"/putaways/{first['id']}/post")
    _putaway(api, wh, other, 1, wh.bin, expect=400)
    topped = _putaway(api, wh, item, 40, wh.bin)
    api.post(f"/putaways/{topped['id']}/post")

    # A move into the full bin is refused; a move out of it and into an empty bin is fine
    bin2 = _bin(api, wh, f"OB{unique}")
    move = {"lines": [{"item_id": item, "uom_id": wh.ea, "qty": 100, "from_location_id": wh.bin, "to_location_id": bin2}]}
    api.post(f"/moves/{api.post('/moves', move)['id']}/post")
    _putaway(api, wh, other, 100, wh.bin)


def test_putaway_sheet_put_is_checked_against_the_bin(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    bin2 = _bin(api, wh, f"PB{unique}")
    item = make_item(api, wh, f"PP{unique}", pallet_qty=100)
    other = make_item(api, wh, f"PQ{unique}", pallet_qty=100)

    held = receive(api, wh, other, 10)  # its sheet reserves the first free bin for `other`
    [reserved] = api.get(f"/putaways/{api.get('/putaways', ref_document_id=held['id'])[0]['id']}")["lines"]
    grn = receive(api, wh, item, 100)
    sheet = api.get(f"/putaways/{api.get('/putaways', ref_document_id=grn['id'])[0]['id']}")
    [line] = sheet["lines"]
    assert line["to_location"]["id"] != reserved["to_location"]["id"]
    assert {line["to_location"]["id"], reserved["to_location"]["id"]} == {wh.bin, bin2}

    put = f"/putaways/{sheet['id']}/lines/{line['id']}/put"
    api.post(put, {"to_location_id": reserved["to_location"]["id"], "qty": 50}, expect=400)  # reserved for another item
    api.post(put, {"to_location_id": line["to_location"]["id"], "qty": 100})
    assert api.post(f"/putaways/{sheet['id']}/post")["status"] == "POSTED"


def test_item_import_needs_a_pallet_quantity(client, admin_headers, unique):
    api = Api(client, admin_headers)
    header = ["SKU code", "Item name", "Base unit", "Qty per pallet"]
    rows = [header, [f"IA{unique}", "No pallet", "EA", None], [f"IB{unique}", "Pallet", "EA", 480], [f"IC{unique}", "In pallets", "PLT", None]]
    result = _import(client, admin_headers, "items", rows, commit=True)
    assert [(e["row"], e["column"]) for e in result["errors"]] == [(2, "Qty per pallet")]
    assert not result["committed"]

    result = _import(client, admin_headers, "items", [header, *rows[2:]], commit=True)
    assert result["committed"], result["errors"]
    [item] = api.get("/items", keyword=f"IB{unique}")
    assert [(p["uom"]["code"], p["factor"]) for p in item["packings"]] == [("PLT", 480)]

    # An existing item keeps its pallet when the cell is empty, and takes a new one when given
    result = _import(client, admin_headers, "items", [header, [f"IB{unique}", "Renamed", "EA", None]], commit=True)
    assert result["committed"], result["errors"]
    result = _import(client, admin_headers, "items", [header, [f"IB{unique}", "Renamed", "EA", 500]], commit=True)
    assert result["committed"], result["errors"]
    [item] = api.get("/items", keyword=f"IB{unique}")
    assert (item["name"], [p["factor"] for p in item["packings"]]) == ("Renamed", [500])
