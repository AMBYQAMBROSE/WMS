"""Live change feed, dashboard freshness and zone occupancy."""

import pytest
from sqlalchemy import select

from tests.helpers import Api, make_item, make_warehouse, put_away, receive


@pytest.fixture
def tenant_id(database):
    from app.core.db import SessionLocal
    from app.models.tenant import Tenant

    with SessionLocal() as db:
        return db.scalar(select(Tenant.id).where(Tenant.code == "DEFAULT"))


@pytest.fixture
def feed(tenant_id):
    """A feed with one tenant registered, primed (first poll only remembers what is already there)"""
    from app.services.live_service import ChangeFeed, _TenantState

    change_feed = ChangeFeed()
    change_feed._tenants[tenant_id] = _TenantState()
    assert change_feed.poll_once() == {}
    return change_feed


def test_feed_reports_new_changes_once(client, admin_headers, unique, feed, tenant_id):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"LV{unique}")

    events = feed.poll_once()[tenant_id]
    assert {"type": "item", "id": item, "parent_id": None, "action": "CREATE", "doc_type": None} in events
    assert {e["type"] for e in events} >= {"item", "location", "business_partner"}
    assert feed.poll_once() == {}, "already sent changes are not sent again"


def test_change_right_after_subscribing_is_not_lost(client, admin_headers, unique, tenant_id):
    """A change committed between subscribing and the feed's first poll is news, not history"""
    from app.services.live_service import ChangeFeed, _TenantState

    change_feed = ChangeFeed()
    change_feed._tenants[tenant_id] = _TenantState()
    api = Api(client, admin_headers)
    item = make_item(api, make_warehouse(api, unique), f"RC{unique}")
    assert item in {e["id"] for e in change_feed.poll_once()[tenant_id]}


def test_feed_names_the_document_type_of_lines(client, admin_headers, unique, feed, tenant_id):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"LD{unique}")
    feed.poll_once()

    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 2}]})
    events = feed.poll_once()[tenant_id]
    header = next(e for e in events if e["type"] == "document")
    line = next(e for e in events if e["type"] == "document_line")
    assert (header["id"], header["doc_type"]) == (po["id"], "PO")
    assert (line["parent_id"], line["doc_type"]) == (po["id"], "PO")


def test_events_carry_no_values(client, admin_headers, unique, feed, tenant_id):
    api = Api(client, admin_headers)
    api.post("/users", {"username": f"lv{unique}", "display_name": "Secret Name", "password": "Live@Test123"})
    events = feed.poll_once()[tenant_id]
    assert "Secret Name" not in str(events) and f"lv{unique}" not in str(events)


def test_dashboard_reflects_a_change_immediately(client, admin_headers, unique):
    """The dashboard is cached for 30 s, but never across a change"""
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"DB{unique}")
    before = api.get("/reports/dashboard")
    receive(api, wh, item, 7)
    after = api.get("/reports/dashboard")
    assert after["today"]["grn_posted"] == before["today"]["grn_posted"] + 1


def test_occupancy_groups_bins_by_zone(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)  # its pickable bin sits directly under the warehouse
    zone = api.post("/locations", {"code": f"Z{unique}", "name": "Zone", "location_type": "ZONE", "parent_id": wh.warehouse})
    rack = api.post("/locations", {"code": f"R{unique}", "name": "Rack", "location_type": "RACK", "parent_id": zone["id"]})
    for n in range(3):
        api.post("/locations", {"code": f"ZB{n}{unique}", "name": "Bin", "location_type": "BIN", "parent_id": rack["id"],
                                "capacity_qty": 100, "is_locked": n == 2})
    item = make_item(api, wh, f"OC{unique}")
    receive(api, wh, item, 5)
    put_away(api, wh, item, 5)

    areas = {a["code"]: a for a in api.get("/reports/occupancy")}
    in_zone = areas[f"Z{unique}"]
    assert (in_zone["bins_total"], in_zone["bins_used"], in_zone["bins_locked"]) == (3, 0, 1)
    assert in_zone["capacity_qty"] == 300
    in_warehouse = areas[f"WH{unique}"]
    assert (in_warehouse["bins_total"], in_warehouse["bins_used"], in_warehouse["qty_on_hand"]) == (1, 1, 5)
    assert in_warehouse["capacity_qty"] is None
