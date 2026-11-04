"""Thin API wrapper for tests: builds master data and walks documents through their state machines."""

from dataclasses import dataclass

from fastapi.testclient import TestClient

PREFIX = "/api/v1"


class Api:
    def __init__(self, client: TestClient, headers: dict[str, str]):
        self.client = client
        self.headers = headers

    def call(self, method: str, path: str, body: dict | None = None, expect: int | None = None, **params):
        response = self.client.request(method, PREFIX + path, json=body, headers=self.headers, params=params or None)
        if expect is None:
            assert response.is_success, f"{method} {path} -> {response.status_code} {response.text}"
        else:
            assert response.status_code == expect, f"{method} {path} -> {response.status_code} {response.text}"
        return response.json() if response.content else None

    def get(self, path: str, **params):
        return self.call("GET", path, **params)

    def post(self, path: str, body: dict | None = None, expect: int | None = None):
        return self.call("POST", path, body, expect)


@dataclass
class Warehouse:
    """One warehouse with a receiving dock, a pickable bin and an outbound staging dock"""

    ea: str
    supplier: str
    customer: str
    dock_in: str
    bin: str
    dock_out: str


def make_warehouse(api: Api, suffix: str) -> Warehouse:
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    supplier = api.post("/business-partners", {"code": f"S{suffix}", "name": "Supplier", "partner_type": "supplier"})
    customer = api.post("/business-partners", {"code": f"C{suffix}", "name": "Customer", "partner_type": "customer"})
    wh = api.post("/locations", {"code": f"WH{suffix}", "name": "Warehouse", "location_type": "WAREHOUSE"})

    def location(code: str, location_type: str, pickable: bool = False) -> str:
        body = {
            "code": f"{code}{suffix}", "name": code, "location_type": location_type,
            "parent_id": wh["id"], "is_pickable": pickable,
        }
        return api.post("/locations", body)["id"]

    return Warehouse(
        ea=ea,
        supplier=supplier["id"],
        customer=customer["id"],
        dock_in=location("IN", "DOCK"),
        bin=location("BIN", "BIN", pickable=True),
        dock_out=location("OUT", "DOCK"),
    )


def make_item(api: Api, wh: Warehouse, sku: str) -> str:
    return api.post("/items", {"sku_code": sku, "name": f"Item {sku}", "base_uom_id": wh.ea})["id"]


def balance(api: Api, item_id: str, location_id: str) -> tuple[float, float]:
    """(on hand, allocated) of an item at a location"""
    rows = [r for r in api.get("/stock/balances", item_id=item_id) if r["location"]["id"] == location_id]
    return (
        sum(float(r["qty_on_hand"]) for r in rows),
        sum(float(r["qty_allocated"]) for r in rows),
    )


def receive(api: Api, wh: Warehouse, item_id: str, qty: float) -> dict:
    """PO -> confirm -> GRN at the receiving dock -> post; returns the posted GRN"""
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item_id, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    grn = api.post("/grns", {
        "po_id": po["id"], "location_id": wh.dock_in,
        "lines": [{"po_line_id": po["lines"][0]["id"], "qty": qty}],
    })
    return api.post(f"/grns/{grn['id']}/post")


def put_away(api: Api, wh: Warehouse, item_id: str, qty: float) -> dict:
    putaway = api.post("/putaways", {"lines": [{
        "item_id": item_id, "uom_id": wh.ea, "qty": qty,
        "from_location_id": wh.dock_in, "to_location_id": wh.bin,
    }]})
    return api.post(f"/putaways/{putaway['id']}/post")
