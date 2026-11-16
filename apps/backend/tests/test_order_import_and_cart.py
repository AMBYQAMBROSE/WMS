"""Excel import of purchase/sales orders, and the shopping cart (customer accounts and internal staff)."""

import io

from openpyxl import Workbook

from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse, put_away, receive

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _import(client, headers, kind: str, rows: list[list], commit: bool) -> dict:
    response = client.post(
        f"/api/v1/imports/{kind}", headers=headers, params={"commit": commit},
        files={"file": ("orders.xlsx", _xlsx(rows), XLSX)},
    )
    assert response.status_code == 200, response.text
    return response.json()


ORDER_HEADER = ["Order ref", "Customer code", "SKU code", "Quantity", "Unit", "Requested ship date", "Remark"]


def test_sales_order_import_groups_rows_into_orders(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    a, b = make_item(api, wh, f"IA{unique}"), make_item(api, wh, f"IB{unique}")
    customer = f"C{unique}"
    rows = [
        ORDER_HEADER,
        ["R1", customer, f"IA{unique}", 3, "EA", "2026-12-31", "first"],
        ["R1", customer, f"IA{unique}", 2, None, "2026-12-31", "first"],  # same item and unit: merged
        ["R1", customer, f"IB{unique}", 1, None, "2026-12-31", "first"],
        ["R2", customer, f"IB{unique}", 5, None, None, None],
    ]

    checked = _import(client, admin_headers, "sales_orders", rows, commit=False)
    assert checked["error_count"] == 0, checked["errors"]
    assert not checked["committed"]
    assert [(d["ref"], d["lines"], d["document_no"]) for d in checked["documents"]] == [("R1", 2, None), ("R2", 1, None)]

    done = _import(client, admin_headers, "sales_orders", rows, commit=True)
    assert done["committed"] and done["created"] == 2
    first = api.get(f"/sales-orders/{done['documents'][0]['document_id']}")
    assert first["status"] == "DRAFT"
    assert first["expected_date"] == "2026-12-31" and first["remark"] == "first"
    assert {(line["item"]["id"], float(line["qty_planned"])) for line in first["lines"]} == {(a, 5.0), (b, 1.0)}


def test_order_import_reports_row_errors_and_writes_nothing(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    make_item(api, wh, f"IE{unique}")
    rows = [
        ["Order ref", "Supplier code", "SKU code", "Quantity", "Unit"],
        ["P1", f"S{unique}", f"IE{unique}", 4, None],
        ["P1", f"C{unique}", f"IE{unique}", 4, None],  # a customer, not a supplier
        ["P2", f"S{unique}", "NO-SUCH-SKU", 1, None],
        ["P3", f"S{unique}", f"IE{unique}", 1, "CTN"],  # no CTN conversion on this item
        ["P4", f"S{unique}", f"IE{unique}", -1, None],
    ]
    result = _import(client, admin_headers, "purchase_orders", rows, commit=True)
    assert not result["committed"]
    assert {(e["row"], e["column"]) for e in result["errors"]} == {
        (3, "Supplier code"), (4, "SKU code"), (5, "Unit"), (6, "Quantity"),
    }
    assert api.get("/purchase-orders", partner_id=wh.supplier) == []


def test_order_import_rejects_header_mismatch_within_one_order(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    make_item(api, wh, f"IM{unique}")
    rows = [
        ORDER_HEADER,
        ["R1", f"C{unique}", f"IM{unique}", 1, None, "2026-12-01", None],
        ["R1", f"C{unique}", f"IM{unique}", 1, None, "2026-12-02", None],
    ]
    result = _import(client, admin_headers, "sales_orders", rows, commit=False)
    assert [(e["row"], e["column"]) for e in result["errors"]] == [(3, "Requested ship date")]


def test_order_import_template_downloads(client, admin_headers):
    for kind in ("purchase_orders", "sales_orders"):
        response = client.get(f"/api/v1/imports/{kind}/template", headers=admin_headers)
        assert response.status_code == 200
        assert response.content[:2] == b"PK"


def _customer_account(api: Api, client, unique: str, partner_id: str) -> Api:
    api.post("/users", {
        "username": f"cust{unique}", "display_name": "Store", "password": "Store@123",
        "role_codes": ["CUSTOMER"], "partner_id": partner_id,
    })
    return Api(client, login(client, f"cust{unique}", "Store@123"))


def test_customer_account_orders_only_for_itself(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"CT{unique}")
    receive(api, wh, item, 10)
    put_away(api, wh, item, 10)
    other = api.post("/business-partners", {"code": f"O{unique}", "name": "Other", "partner_type": "customer"})
    store = _customer_account(api, client, unique, wh.customer)

    me = store.get("/auth/me")
    assert me["partner"]["id"] == wh.customer
    assert [c["id"] for c in store.get("/cart/customers")] == [wh.customer]

    page = store.get("/cart/catalog", keyword=f"CT{unique}")
    assert page["total"] == 1
    assert float(page["items"][0]["available"]) == 10
    assert page["items"][0]["uoms"][0]["id"] == wh.ea

    # No partner given: its own customer is used; duplicate lines are merged
    line = {"item_id": item, "uom_id": wh.ea, "qty": 2}
    so = store.post("/cart/orders", {"lines": [line, line], "remark": "weekly"})
    assert so["status"] == "DRAFT" and so["partner"]["id"] == wh.customer
    assert [float(line["qty_planned"]) for line in so["lines"]] == [4.0]

    # Cannot order for another customer, and has no access to the normal sales order screens
    store.call("POST", "/cart/orders", {"partner_id": other["id"], "lines": [line]}, expect=403)
    store.call("GET", "/sales-orders", expect=403)

    # Sees orders for its customer, including ones staff entered for it, but not other customers' orders
    staff_so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [line]})
    other_so = api.post("/sales-orders", {"partner_id": other["id"], "lines": [line]})
    mine = {o["id"] for o in store.get("/cart/orders")}
    assert {so["id"], staff_so["id"]} <= mine and other_so["id"] not in mine
    store.call("GET", f"/cart/orders/{other_so['id']}", expect=404)

    # May withdraw a draft, not a confirmed order
    assert store.post(f"/cart/orders/{so['id']}/cancel")["status"] == "CANCELLED"
    api.post(f"/sales-orders/{staff_so['id']}/confirm")
    store.call("POST", f"/cart/orders/{staff_so['id']}/cancel", expect=400)


def test_staff_cart_needs_a_customer_and_sees_own_orders(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"ST{unique}")
    line = {"item_id": item, "uom_id": wh.ea, "qty": 1}

    api.call("POST", "/cart/orders", {"lines": [line]}, expect=400)
    so = api.post("/cart/orders", {"partner_id": wh.customer, "lines": [line]})
    assert so["id"] in {o["id"] for o in api.get("/cart/orders")}
    # Out-of-stock items are listed (ordering ahead is allowed) unless asked for in-stock only
    assert api.get("/cart/catalog", keyword=f"ST{unique}")["total"] == 1
    assert api.get("/cart/catalog", keyword=f"ST{unique}", in_stock_only=True)["total"] == 0


def test_user_can_only_be_linked_to_a_customer(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    api.call("POST", "/users", {
        "username": f"bad{unique}", "display_name": "Bad", "password": "Bad@1234", "partner_id": wh.supplier,
    }, expect=400)
