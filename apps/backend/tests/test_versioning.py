"""Optimistic locking: an edit based on an outdated copy is refused instead of silently overwriting someone's change."""

from tests.helpers import Api, make_item, make_warehouse


def test_stale_item_edit_is_refused(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = api.get(f"/items/{make_item(api, wh, f'OL{unique}')}")
    loaded = item["row_version"]

    # Someone else saves first
    theirs = api.call("PUT", f"/items/{item['id']}", {"name": "Their name", "row_version": loaded})
    assert theirs["row_version"] > loaded

    # My save, from the copy I opened before theirs
    response = client.put(f"/api/v1/items/{item['id']}", headers=admin_headers, json={"name": "My name", "row_version": loaded})
    assert response.status_code == 409
    assert "changed by someone else" in response.json()["detail"]
    assert api.get(f"/items/{item['id']}")["name"] == "Their name"

    # Reloaded, it goes through
    mine = api.call("PUT", f"/items/{item['id']}", {"name": "My name", "row_version": theirs["row_version"]})
    assert mine["name"] == "My name"


def test_edit_without_a_version_still_works(client, admin_headers, unique):
    """Older clients (PDA, integrations) that do not send row_version keep working, without the check"""
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"NV{unique}")
    assert api.call("PUT", f"/items/{item}", {"name": "No version"})["name"] == "No version"


def test_stale_draft_order_edit_is_refused(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"OD{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})

    def body(qty: int, version: int) -> dict:
        return {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}], "row_version": version}

    first = api.call("PUT", f"/purchase-orders/{po['id']}", body(2, po["row_version"]))
    api.call("PUT", f"/purchase-orders/{po['id']}", body(9, po["row_version"]), expect=409)
    assert api.get(f"/purchase-orders/{po['id']}")["lines"][0]["qty_planned"] == 2
    assert first["row_version"] > po["row_version"]


def test_every_kind_of_change_bumps_the_version(client, admin_headers, unique):
    """Status changes count too, so an edit form opened before a confirm cannot save over the confirmed order"""
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"BV{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})
    confirmed = api.post(f"/purchase-orders/{po['id']}/confirm")
    assert confirmed["row_version"] > po["row_version"]

    location = api.get("/locations", keyword=f"BIN{unique}")[0]
    locked = api.call("PUT", f"/locations/{location['id']}", {"is_locked": True})
    assert locked["row_version"] > location["row_version"]


def test_role_edits_are_versioned(client, admin_headers, unique):
    api = Api(client, admin_headers)
    role = api.post("/roles", {"code": f"V{unique}", "name": "Versioned", "permission_codes": ["item.read"]})
    api.call("PUT", f"/roles/{role['id']}", {"name": "Renamed", "permission_codes": ["item.read"], "row_version": role["row_version"]})
    api.call("PUT", f"/roles/{role['id']}", {"name": "Again", "permission_codes": ["item.read"], "row_version": role["row_version"]}, expect=409)


def test_simultaneous_saves_of_the_same_version_cannot_both_win(client, admin_headers, unique):
    """check_version re-reads under an update lock: the second save waits for the first, then sees its new version"""
    import threading
    import uuid

    from app.core.db import SessionLocal
    from app.core.errors import ConflictError
    from app.models.item import Item
    from app.repositories.base import check_version

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item_id = uuid.UUID(make_item(api, wh, f"CC{unique}"))
    version = api.get(f"/items/{item_id}")["row_version"]

    first_has_lock = threading.Event()
    release_first = threading.Event()
    outcome: dict[str, str] = {}

    def save(name: str, hold: bool) -> None:
        with SessionLocal() as db:
            item = db.get(Item, item_id)
            try:
                check_version(item, version, "Item")
            except ConflictError:
                outcome[name] = "conflict"
                return
            if hold:
                first_has_lock.set()
                release_first.wait(10)
            item.name = name
            db.commit()
            outcome[name] = "saved"

    first = threading.Thread(target=save, args=("first", True))
    first.start()
    assert first_has_lock.wait(10)
    second = threading.Thread(target=save, args=("second", False))
    second.start()
    second.join(1)
    assert second.is_alive(), "the second save must wait for the first one's lock"
    release_first.set()
    first.join(10)
    second.join(10)
    assert outcome == {"first": "saved", "second": "conflict"}
    assert api.get(f"/items/{item_id}")["name"] == "first"
