"""Document list filters and per-user preferences (saved views, columns)."""

from datetime import date, timedelta

from app.services.report_service import today_local
from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse


def _po(api: Api, wh, item: str, remark: str | None = None) -> dict:
    body = {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}], "remark": remark}
    return api.post("/purchase-orders", body)


def test_keyword_matches_number_partner_and_remark(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"KW{unique}")
    po = _po(api, wh, item, remark=f"urgent-{unique}")

    def found(keyword: str) -> bool:
        return po["id"] in {d["id"] for d in api.get("/purchase-orders", keyword=keyword, limit=500)}

    assert found(po["doc_no"][-6:])
    assert found(f"S{unique}")  # supplier code
    assert found(f"urgent-{unique}")
    assert not found(f"nothing-{unique}")


def test_created_date_range(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    po = _po(api, wh, make_item(api, wh, f"DR{unique}"))
    today = today_local()

    def found(**params) -> bool:
        return po["id"] in {d["id"] for d in api.get("/purchase-orders", keyword=po["doc_no"], **params)}

    assert found(created_from=today.isoformat(), created_to=today.isoformat())
    assert not found(created_from=(today + timedelta(days=1)).isoformat())
    assert not found(created_to=(today - timedelta(days=1)).isoformat())


def test_filters_apply_to_every_document_list(client, admin_headers):
    api = Api(client, admin_headers)
    for path in ["purchase-orders", "grns", "putaways", "moves", "adjustments", "cycle-counts",
                 "sales-orders", "picks", "shipments"]:
        assert api.get(f"/{path}", keyword="no-such-document-xyz", created_from=date.today().isoformat()) == [], path


def test_preferences_are_per_user(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    key = f"/me/preferences/list:test-{unique.lower()}"
    assert admin.get(key)["value"] is None

    views = {"views": [{"name": "Drafts this week", "filters": {"status": "DRAFT"}}], "hidden": ["remark"]}
    admin.call("PUT", key, {"value": views})
    assert admin.get(key)["value"] == views

    admin.post("/users", {"username": f"pref{unique}", "display_name": "P", "password": "Pref@Test123"})
    other = Api(client, login(client, f"pref{unique}", "Pref@Test123"))
    assert other.get(key)["value"] is None, "another user does not see my settings"


def test_preference_key_and_size_are_validated(client, admin_headers):
    api = Api(client, admin_headers)
    api.call("PUT", "/me/preferences/Bad Key!", {"value": 1}, expect=422)
    api.call("PUT", "/me/preferences/list:big", {"value": "x" * 40_000}, expect=413)


def test_keyword_matches_the_source_document_number(client, admin_headers, unique):
    from tests.helpers import receive

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    grn = receive(api, wh, make_item(api, wh, f"SR{unique}"), 2)
    po_no = grn["ref_document"]["doc_no"]
    assert grn["id"] in {d["id"] for d in api.get("/grns", keyword=po_no)}
