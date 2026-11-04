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
