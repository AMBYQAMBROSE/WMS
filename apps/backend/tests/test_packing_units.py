"""Packing units on the item master: receive and ship in cartons / pallets, stock is kept in the base unit."""

from tests.helpers import Api, balance, make_warehouse


def _uom(api: Api, code: str) -> str:
    return next(u["id"] for u in api.get("/uoms") if u["code"] == code)


def _packed_item(api: Api, wh, sku: str) -> tuple[str, str, str]:
    """Item in EA with CTN = 12 EA and PLT = 480 EA; returns (item, ctn, plt)"""
    ctn, plt = _uom(api, "CTN"), _uom(api, "PLT")
    item = api.post("/items", {
        "sku_code": sku, "name": f"Item {sku}", "base_uom_id": wh.ea,
        "packings": [{"uom_id": plt, "factor": 480}, {"uom_id": ctn, "factor": 12}],
    })
    assert [(p["uom"]["code"], p["factor"]) for p in item["packings"]] == [("CTN", 12), ("PLT", 480)]
    return item["id"], ctn, plt


def test_receive_in_pallets_and_ship_in_cartons(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item, ctn, plt = _packed_item(api, wh, f"PK{unique}")

    # Ordered in eaches, counted in pallets at the dock: 2 PLT = 960 EA on the dock and the order fully received
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 960}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {
        "po_id": po["id"], "location_id": wh.dock_in,
        "lines": [{"po_line_id": po["lines"][0]["id"], "qty": 2, "uom_id": plt}],
    })
    assert grn["lines"][0]["uom"]["code"] == "PLT"
    api.post(f"/grns/{grn['id']}/post")
    assert balance(api, item, wh.dock_in)[0] == 960
    assert api.get(f"/purchase-orders/{po['id']}")["status"] == "RECEIVED"

    putaway = api.post("/putaways", {"lines": [{
        "item_id": item, "uom_id": wh.ea, "qty": 960, "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    api.post(f"/putaways/{putaway['id']}/post")

    # Delivery order in cartons: 5 CTN takes 60 EA out of the bin
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": ctn, "qty": 5}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    assert balance(api, item, wh.bin) == (960, 60)
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    shipment = api.post("/shipments", {"so_id": so["id"]})
    api.post(f"/shipments/{shipment['id']}/post")
    assert balance(api, item, wh.bin) == (900, 0)
    assert balance(api, item, wh.dock_out)[0] == 0


def test_receipt_in_a_smaller_unit_must_come_out_exact(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item, ctn, _ = _packed_item(api, wh, f"PX{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": ctn, "qty": 10}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    line = po["lines"][0]["id"]

    api.call("POST", "/grns", {"po_id": po["id"], "location_id": wh.dock_in,
                               "lines": [{"po_line_id": line, "qty": 5, "uom_id": wh.ea}]}, expect=400)
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in,
                             "lines": [{"po_line_id": line, "qty": 24, "uom_id": wh.ea}]})
    api.post(f"/grns/{grn['id']}/post")
    assert balance(api, item, wh.dock_in)[0] == 24
    po = api.get(f"/purchase-orders/{po['id']}")
    assert po["status"] == "PARTIALLY_RECEIVED" and po["lines"][0]["qty_actual"] == 2


def test_unit_without_packing_is_refused(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = api.post("/items", {"sku_code": f"PN{unique}", "name": "No packing", "base_uom_id": wh.ea})["id"]
    api.call("POST", "/sales-orders", {"partner_id": wh.customer,
                                       "lines": [{"item_id": item, "uom_id": _uom(api, "CTN"), "qty": 1}]}, expect=400)


def test_packing_rules(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    ctn, plt = _uom(api, "CTN"), _uom(api, "PLT")
    sku = f"PR{unique}"

    api.call("POST", "/items", {"sku_code": sku, "name": "x", "base_uom_id": wh.ea,
                                "packings": [{"uom_id": wh.ea, "factor": 1}]}, expect=400)
    api.call("POST", "/items", {"sku_code": sku, "name": "x", "base_uom_id": wh.ea,
                                "packings": [{"uom_id": ctn, "factor": 12}, {"uom_id": ctn, "factor": 6}]}, expect=400)
    api.call("POST", "/items", {"sku_code": sku, "name": "x", "base_uom_id": wh.ea,
                                "packings": [{"uom_id": ctn, "factor": 0}]}, expect=422)

    item = api.post("/items", {"sku_code": sku, "name": "x", "base_uom_id": wh.ea, "packings": [{"uom_id": ctn, "factor": 12}]})
    # Not used yet: free to change
    item = api.call("PUT", f"/items/{item['id']}", {"row_version": item["row_version"], "packings": [{"uom_id": ctn, "factor": 10}]})
    assert [p["factor"] for p in item["packings"]] == [10]
    # Editing other fields leaves the packings alone
    item = api.call("PUT", f"/items/{item['id']}", {"row_version": item["row_version"], "name": "renamed"})
    assert len(item["packings"]) == 1

    api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item["id"], "uom_id": ctn, "qty": 1}]})
    # Used by a document: the factor is fixed and the unit cannot be dropped, but more units can be added
    for packings in ([{"uom_id": ctn, "factor": 12}], []):
        api.call("PUT", f"/items/{item['id']}", {"row_version": item["row_version"], "packings": packings}, expect=409)
    item = api.call("PUT", f"/items/{item['id']}", {
        "row_version": item["row_version"], "packings": [{"uom_id": ctn, "factor": 10}, {"uom_id": plt, "factor": 400}],
    })
    assert [p["uom"]["code"] for p in item["packings"]] == ["CTN", "PLT"]
