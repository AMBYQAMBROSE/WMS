"""Master data rules."""

from tests.helpers import Api


def test_duplicate_item_code_is_a_conflict(client, admin_headers, unique):
    api = Api(client, admin_headers)
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    api.post("/items", {"sku_code": f"DUP{unique}", "name": "First", "base_uom_id": ea})
    api.post("/items", {"sku_code": f"DUP{unique}", "name": "Second", "base_uom_id": ea}, expect=409)


def test_partner_type_is_validated(client, admin_headers, unique):
    api = Api(client, admin_headers)
    api.call("POST", "/business-partners", {"code": f"P{unique}", "name": "P", "partner_type": "vendor"}, expect=422)


def test_location_path_follows_parent(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = api.post("/locations", {"code": f"W{unique}", "name": "W", "location_type": "WAREHOUSE"})
    bin_ = api.post("/locations", {"code": f"B{unique}", "name": "B", "location_type": "BIN", "parent_id": wh["id"]})
    assert bin_["path"].startswith(wh["path"])
    assert bin_["path"] != wh["path"]


def test_item_search_reads_gs1_codes(client, admin_headers, unique):
    """Scanning a supplier's GS1 carton code or our stock label into a web item field finds the item"""
    api = Api(client, admin_headers)
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    ean = f"69{int(unique, 16) % 10**11:011d}"  # 13 digits, unique per run
    item = api.post("/items", {"sku_code": f"G{unique}", "name": "GS1 item", "barcode": ean, "base_uom_id": ea})
    carton = f"]C101{ean.zfill(14)}17271231" + f"10L{unique}\x1d3024"
    assert [i["id"] for i in api.get("/items", keyword=carton)] == [item["id"]]
    label = f"(240)G{unique}(10)L1(17)270531(30)24"
    assert [i["id"] for i in api.get("/items", keyword=label)] == [item["id"]]
