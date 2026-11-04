"""Field-level audit log: what is recorded, how it reads, and that it follows the business transaction."""

from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse


def history(api: Api, entity_id: str) -> list[dict]:
    """Oldest first"""
    return list(reversed(api.get("/audit-logs", entity_id=entity_id)))


def changes(entry: dict) -> dict:
    return {c["field"]: (c["old"], c["new"]) for c in entry["changes"]}


def test_item_create_update_delete(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"AU{unique}")
    api.call("PUT", f"/items/{item}", {"name": "Renamed"})
    api.call("DELETE", f"/items/{item}")

    created, updated, deleted = history(api, item)
    assert (created["action"], updated["action"], deleted["action"]) == ("CREATE", "UPDATE", "DELETE")
    assert created["entity_type"] == "item" and created["entity_label"] == f"AU{unique}"
    assert created["username"] == "admin"
    # Referenced records are shown by code, not id
    assert changes(created)["base_uom_id"] == (None, "EA")
    # Only what changed, without bookkeeping columns
    assert changes(updated) == {"name": (f"Item AU{unique}", "Renamed")}
    assert changes(deleted) == {"is_deleted": (False, True)}


def test_document_history_includes_lines_and_status(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"AD{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")

    entries = history(api, po["id"])
    header_created = next(e for e in entries if e["entity_type"] == "document" and e["action"] == "CREATE")
    assert changes(header_created)["partner_id"] == (None, f"S{unique}")
    line_created = next(e for e in entries if e["entity_type"] == "document_line")
    assert line_created["parent_id"] == po["id"]
    assert line_created["entity_label"] == f"{po['doc_no']} line 1"
    assert changes(line_created)["document_id"] == (None, po["doc_no"])
    assert changes(line_created)["item_id"] == (None, f"AD{unique}")
    assert changes(line_created)["qty_planned"] == (None, 5)
    confirmed = [e for e in entries if e["action"] == "UPDATE" and "status" in changes(e)]
    assert changes(confirmed[-1])["status"] == ("DRAFT", "CONFIRMED")


def test_document_numbering_counter_is_not_logged(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"NC{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})
    rule_changes = [r for r in api.get("/audit-logs", entity_type="doc_number_rule", limit=500)
                    if r["occurred_at"] >= po["created_at"][:19]]
    assert rule_changes == []


def test_secrets_are_masked(client, admin_headers, unique):
    api = Api(client, admin_headers)
    user = api.post("/users", {"username": f"mask{unique}", "display_name": "M", "password": "Mask@Test123"})
    api.post(f"/users/{user['id']}/reset-password", {"password": "Mask@Test456"})

    entries = history(api, user["id"])
    assert changes(entries[0])["password_hash"] == (None, "***")
    assert changes(entries[-1])["password_hash"] == ("***", "***")
    assert "Mask@" not in str(entries)


def test_role_permissions_and_user_roles_are_recorded(client, admin_headers, unique):
    api = Api(client, admin_headers)
    role = api.post("/roles", {"code": f"R{unique}", "name": "Role", "permission_codes": ["item.read"]})
    api.call("PUT", f"/roles/{role['id']}", {"name": "Role", "permission_codes": ["item.read", "stock.read"]})
    user = api.post("/users", {"username": f"ro{unique}", "display_name": "R", "password": "Role@Test123", "role_codes": [f"R{unique}"]})

    permission_changes = [changes(e)["permissions"] for e in history(api, role["id"]) if "permissions" in changes(e)]
    assert permission_changes == [([], ["item.read"]), (["item.read"], ["item.read", "stock.read"])]
    role_changes = [changes(e)["roles"] for e in history(api, user["id"]) if "roles" in changes(e)]
    assert role_changes == [([], [f"R{unique}"])]


def test_rolled_back_request_leaves_no_audit_row(client, admin_headers, unique):
    """Removing your own user-management permission fails after the roles were already rewritten in the transaction"""
    admin = Api(client, admin_headers)
    password = "Self@Test123"
    user = admin.post("/users", {"username": f"self{unique}", "display_name": "S", "password": password, "role_codes": ["ADMIN"]})
    me = Api(client, login(client, f"self{unique}", password))
    me.call("PUT", f"/users/{user['id']}", {"display_name": "S", "role_codes": []}, expect=400)

    role_changes = [changes(e)["roles"] for e in history(admin, user["id"]) if "roles" in changes(e)]
    assert role_changes == [([], ["ADMIN"])], "only the committed assignment, not the rolled-back removal"


def test_audit_rows_carry_the_request_id(client, admin_headers, unique):
    api = Api(client, admin_headers)
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    response = client.post("/api/v1/items", headers=admin_headers, json={"sku_code": f"RQ{unique}", "name": "x", "base_uom_id": ea})
    request_id = response.headers["x-request-id"]
    assert request_id
    assert history(api, response.json()["id"])[0]["request_id"] == request_id


def test_audit_log_requires_permission(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    admin.post("/users", {"username": f"na{unique}", "display_name": "N", "password": "None@Test123"})
    Api(client, login(client, f"na{unique}", "None@Test123")).call("GET", "/audit-logs", expect=403)


def test_filter_by_keyword_and_action(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    make_item(api, wh, f"KW{unique}")
    rows = api.get("/audit-logs", keyword=f"KW{unique}", action="CREATE")
    assert [r["entity_label"] for r in rows] == [f"KW{unique}"]
