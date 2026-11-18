"""Purchase prices and who sees them, supplier payables, dashboard trend analysis, low-stock alarms, recipe costing and
the real-time stock-on-hand export."""

import csv
import io
import time
import uuid
from datetime import timedelta

import pytest

from app.core.db import SessionLocal
from app.models.item import Item
from app.services import report_service
from app.services.analytics_service import AnalyticsService
from tests.conftest import login
from tests.helpers import Api, make_warehouse, put_away


@pytest.fixture(autouse=True)
def fresh_reports():
    """Dashboard and analytics results are cached per tenant; every call in these tests must see the data just made"""
    report_service._report_cache.clear()
    yield
    report_service._report_cache.clear()


def _uom(api: Api, code: str) -> str:
    return next(u["id"] for u in api.get("/uoms") if u["code"] == code)


def _no_cost_user(client, admin: Api, unique: str) -> Api:
    """Can work with orders, receipts, reports, stock and recipes, but has no cost.view"""
    role = admin.post("/roles", {"code": f"NC{unique}", "name": "No costs", "permission_codes": [
        "purchase_order.read", "purchase_order.update", "grn.read", "report.read", "stock.read", "recipe.read", "audit.read"]})
    admin.post("/users", {"username": f"nc{unique}", "display_name": "N", "password": "NoCost@Test123", "role_codes": [role["code"]]})
    return Api(client, login(client, f"nc{unique}", "NoCost@Test123"))


def _priced_receipt(api: Api, wh, item: str, uom: str, qty: float, price: float, receive_uom: str | None = None,
                    receive_qty: float | None = None) -> tuple[dict, dict]:
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": uom, "qty": qty, "unit_price": price}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    line = {"po_line_id": po["lines"][0]["id"], "qty": receive_qty or qty}
    if receive_uom:
        line["uom_id"] = receive_uom
    grn = api.post("/grns", {"po_id": po["id"], "location_id": wh.dock_in, "lines": [line]})
    return po, api.post(f"/grns/{grn['id']}/post")


def test_prices_follow_receipts_and_stay_hidden_without_cost_view(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    ctn = _uom(admin, "CTN")
    item = admin.post("/items", {"sku_code": f"PR{unique}", "name": "Priced", "base_uom_id": wh.ea,
                                 "packings": [{"uom_id": ctn, "factor": 12}]})["id"]
    admin.call("PUT", f"/business-partners/{wh.supplier}", {"credit_terms_days": 30})

    # Ordered in eaches at 2.5, received in cartons: the receipt line's price is per carton
    po, grn = _priced_receipt(admin, wh, item, wh.ea, 24, 2.5, receive_uom=ctn, receive_qty=2)
    assert po["lines"][0]["unit_price"] == 2.5
    assert grn["lines"][0]["unit_price"] == 30
    assert grn["payment_due_date"] == str(report_service.today_local() + timedelta(days=30))
    assert grn["settled_on"] is None

    viewer = _no_cost_user(client, admin, unique)
    assert viewer.get(f"/purchase-orders/{po['id']}")["lines"][0]["unit_price"] is None
    assert viewer.get(f"/grns/{grn['id']}")["lines"][0]["unit_price"] is None
    viewer.call("GET", "/reports/pricing", expect=403)
    viewer.call("GET", "/payables", expect=403)
    # The audit log does not give the price away either
    history = viewer.get("/audit-logs", entity_id=po["id"])
    prices = [c for e in history for c in e["changes"] if c["field"] == "unit_price"]
    assert prices and all(c["new"] in (None, "***") for c in prices)

    # Editing a draft without cost.view keeps the saved price instead of wiping it
    draft = admin.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5, "unit_price": 3}]})
    viewer.call("PUT", f"/purchase-orders/{draft['id']}", {
        "partner_id": wh.supplier, "row_version": draft["row_version"], "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 6}]})
    assert admin.get(f"/purchase-orders/{draft['id']}")["lines"][0]["unit_price"] == 3

    # Payables: open until settled, and settling can be undone
    page = admin.get("/payables", partner_id=wh.supplier)
    assert page["total"] == 1 and page["outstanding"] == 60
    row = page["rows"][0]
    assert row["doc_no"] == grn["doc_no"] and row["status"] == "open" and row["value"] == 60 and row["credit_terms_days"] == 30
    admin.call("POST", f"/payables/{grn['id']}/settle", {"settled_on": str(report_service.today_local() + timedelta(days=1))}, expect=400)
    settled = admin.call("POST", f"/payables/{grn['id']}/settle", {"settled_on": str(report_service.today_local())})
    assert settled["settled_on"] == str(report_service.today_local())
    assert admin.get("/payables", partner_id=wh.supplier, status="open")["total"] == 0
    assert admin.get("/payables", partner_id=wh.supplier, status="settled")["rows"][0]["days_overdue"] == -30
    admin.post(f"/payables/{grn['id']}/reopen")
    assert admin.get("/payables", partner_id=wh.supplier, status="open")["total"] == 1

    pricing = admin.get("/reports/pricing", item_id=item)
    row = next(r for r in pricing["rows"] if r["item"]["id"] == item)
    assert row["latest_cost"] == 2.5 and row["avg_cost_ytd"] == 2.5
    assert row["points"][-1]["avg_cost"] == 2.5 and row["points"][-1]["qty"] == 24


def test_dashboard_trends_compare_periods(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    ctn = _uom(admin, "CTN")
    item = admin.post("/items", {"sku_code": f"TR{unique}", "name": "Trend", "base_uom_id": wh.ea,
                                 "packings": [{"uom_id": ctn, "factor": 10}]})["id"]
    admin.call("PUT", f"/business-partners/{wh.supplier}", {"credit_terms_days": 45})
    # The test database is shared and never cleaned: quantities growing with the clock keep this run's SKU and
    # supplier at the top of the ranked tables
    qty = int(time.time()) * 10
    first = admin.get("/reports/analytics")
    before, before_ytd = first["months"][-1]["purchased_qty"], first["totals"]["purchases"]["ytd"]
    before_loss = first["totals"]["losses"]["mtd"]
    report_service._report_cache.clear()
    _priced_receipt(admin, wh, item, wh.ea, qty, 1)
    put_away(admin, wh, item, 100)
    reason = next(r["id"] for r in admin.get("/reason-codes") if r["code"] == "DAMAGE")
    adjustment = admin.post("/adjustments", {"reason_code_id": reason, "lines": [
        {"item_id": item, "uom_id": wh.ea, "location_id": wh.bin, "qty": -40}]})
    admin.post(f"/adjustments/{adjustment['id']}/post")

    data = admin.get("/reports/analytics")
    assert set(data["periods"]) == {"mtd", "mtd_ly", "ytd", "ytd_ly", "last_year", "three_years"}
    assert data["periods"]["ytd"]["start"] == f"{report_service.today_local().year}-01-01"
    assert len(data["months"]) == 12 * 3 + report_service.today_local().month
    assert data["months"][-1]["purchased_qty"] - before == qty
    assert data["totals"]["purchases"]["ytd"] - before_ytd == qty
    assert data["totals"]["losses"]["mtd"] - before_loss == 40
    assert data["totals"]["purchases"]["ytd_value"] is not None

    purchase = data["purchases"]["rows"][0]
    assert purchase["item"]["id"] == item
    assert purchase["mtd"] == purchase["ytd"] == qty and purchase["ytd_ly"] == 0 and purchase["avg_3y"] == 0
    assert purchase["packing"]["factor"] == 10 and purchase["packing"]["uom"]["code"] == "CTN"
    assert purchase["ytd_value"] == qty

    loss = next(r for r in data["losses"]["rows"] if r["item"]["id"] == item)
    assert loss["ytd"] == 40 and loss["ytd_value"] == 40  # at the average purchase cost of 1

    supplier = data["suppliers"]["rows"][0]
    assert supplier["partner"]["id"] == wh.supplier
    assert supplier["credit_terms_days"] == 45 and supplier["ytd_value"] == qty and supplier["receipts"] == 1
    assert supplier["outstanding"] == qty and supplier["open_receipts"] == 1 and supplier["overdue"] == 0

    report_service._report_cache.clear()
    hidden = _no_cost_user(client, admin, unique).get("/reports/analytics")
    assert hidden["purchases"]["rows"][0]["ytd_value"] is None
    assert hidden["months"][-1]["purchased_value"] is None
    assert hidden["totals"]["purchases"]["ytd_value"] is None and hidden["totals"]["purchases"]["ytd"] > 0
    assert all(r["outstanding"] is None for r in hidden["suppliers"]["rows"])
    assert hidden["suppliers"]["outstanding"] is None


def test_low_stock_alarm(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    out = admin.post("/items", {"sku_code": f"LO{unique}", "name": "Out", "base_uom_id": wh.ea, "min_stock_qty": 10})["id"]
    below = admin.post("/items", {"sku_code": f"LB{unique}", "name": "Below", "base_uom_id": wh.ea, "min_stock_qty": 100})["id"]
    fine = admin.post("/items", {"sku_code": f"LF{unique}", "name": "Fine", "base_uom_id": wh.ea, "min_stock_qty": 10})["id"]
    _priced_receipt(admin, wh, below, wh.ea, 50, 1)
    _priced_receipt(admin, wh, fine, wh.ea, 50, 1)

    # The dashboard lists the 50 most urgent; earlier runs leave their own alarms in the shared database, so read them all
    with SessionLocal() as db:
        tenant_id = db.get(Item, uuid.UUID(out)).tenant_id
        alerts = AnalyticsService(db, tenant_id).stock_alerts(limit=1_000_000)
    rows = {str(r["item"]["id"]): r for r in alerts["rows"]}
    assert rows[out]["level"] == "out" and rows[out]["shortfall"] == 10
    assert rows[below]["level"] == "below" and rows[below]["available"] == 50
    assert fine not in rows
    assert alerts["alarm_count"] >= 2

    dashboard = admin.get("/reports/dashboard")
    assert dashboard["stock_alerts"]["alarm_count"] >= 2
    assert admin.get(f"/items/{out}")["min_stock_qty"] == 10


def test_recipe_costing_and_what_stock_can_make(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    ctn = _uom(admin, "CTN")
    flour = admin.post("/items", {"sku_code": f"RA{unique}", "name": "Flour", "base_uom_id": wh.ea})["id"]
    sugar = admin.post("/items", {"sku_code": f"RB{unique}", "name": "Sugar", "base_uom_id": wh.ea,
                                  "packings": [{"uom_id": ctn, "factor": 10}]})["id"]
    cake = admin.post("/items", {"sku_code": f"RP{unique}", "name": "Cake", "base_uom_id": wh.ea})["id"]
    _priced_receipt(admin, wh, flour, wh.ea, 100, 3)
    _priced_receipt(admin, wh, flour, wh.ea, 100, 2)  # the latest price counts
    _priced_receipt(admin, wh, sugar, wh.ea, 100, 0.5)

    body = {"code": f"RC{unique}", "name": "Cake batch", "product_item_id": cake, "output_qty": 10, "lines": [
        {"item_id": flour, "uom_id": wh.ea, "qty": 5}, {"item_id": sugar, "uom_id": ctn, "qty": 2}]}
    admin.call("PUT", "/features/RECIPES", {"enabled": False})
    admin.call("POST", "/recipes", body, expect=403)
    admin.call("PUT", "/features/RECIPES", {"enabled": True})
    try:
        recipe = admin.post("/recipes", body)
        admin.call("POST", "/recipes", body, expect=409)
        costing = admin.get(f"/recipes/{recipe['id']}/costing")
        assert costing["complete"] and costing["unit_cost"] == 2 and costing["batch_cost"] == 20
        lines = {line["item"]["id"]: line for line in costing["lines"]}
        assert lines[flour]["qty_per_unit"] == 0.5 and lines[flour]["unit_cost"] == 2 and lines[flour]["share_pct"] == 50
        assert lines[sugar]["qty_per_unit"] == 2 and lines[sugar]["cost_per_unit"] == 1
        # 200 flour make 400 cakes, 100 sugar only 50
        assert costing["can_make"] == 50 and costing["bottleneck"]["id"] == sugar

        overview = next(r for r in admin.get("/recipes/overview") if r["id"] == recipe["id"])
        assert overview["unit_cost"] == 2 and overview["can_make"] == 50

        viewer = _no_cost_user(client, admin, unique)
        hidden = viewer.get(f"/recipes/{recipe['id']}/costing")
        assert hidden["unit_cost"] is None and all(line["unit_cost"] is None for line in hidden["lines"])
        assert hidden["can_make"] == 50

        # A component without any price makes the costing incomplete (and with no stock, nothing can be made)
        unpriced = admin.post("/items", {"sku_code": f"RU{unique}", "name": "Unpriced", "base_uom_id": wh.ea})["id"]
        updated = admin.call("PUT", f"/recipes/{recipe['id']}", {**body, "row_version": recipe["row_version"],
                                                                 "lines": [*body["lines"], {"item_id": unpriced, "uom_id": wh.ea, "qty": 1}]})
        costing = admin.get(f"/recipes/{updated['id']}/costing")
        assert not costing["complete"] and costing["missing_costs"] == [f"RU{unique}"] and costing["can_make"] == 0

        admin.call("DELETE", f"/items/{flour}", expect=409)
        admin.call("DELETE", f"/recipes/{recipe['id']}")
        admin.call("GET", f"/recipes/{recipe['id']}", expect=404)
    finally:
        admin.call("PUT", "/features/RECIPES", {"enabled": False})


def test_stock_on_hand_export(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    wh = make_warehouse(admin, unique)
    item = admin.post("/items", {"sku_code": f"EX{unique}", "name": "Export", "base_uom_id": wh.ea})["id"]
    _priced_receipt(admin, wh, item, wh.ea, 20, 1.5)
    put_away(admin, wh, item, 5)

    def export(headers, **params):
        response = client.get("/api/v1/reports/stock-on-hand", headers=headers, params=params)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        return [r for r in csv.DictReader(io.StringIO(response.text.lstrip("﻿"))) if r["SKU"] == f"EX{unique}"]

    rows = export(admin_headers)
    assert sorted((r["Location"], r["On hand"]) for r in rows) == sorted([(f"BIN{unique}", "5"), (f"IN{unique}", "15")])
    assert {r["Stock value"] for r in rows} == {"7.5", "22.5"}
    [summary] = export(admin_headers, by="item")
    assert summary["On hand"] == "20" and summary["Locations"] == "2" and summary["Stock value"] == "30"

    viewer = _no_cost_user(client, admin, unique)
    [hidden] = export(viewer.headers, by="item")
    assert "Stock value" not in hidden and hidden["Available"] == "20"
