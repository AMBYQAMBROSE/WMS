"""Master data and stock helpers shared by the recorded flow batches (checklist section 0)."""

import datetime
from dataclasses import dataclass

from tests.e2e.flows.conftest import add_conversion
from tests.helpers import Api

TODAY = datetime.date.today()


@dataclass
class Scenario:
    u: str
    ea: str
    ctn: str
    supplier: str
    supplier_code: str
    inactive_supplier: str
    customer: str
    customer_code: str
    customer2: str
    warehouse: str
    dock_in: str
    stage: str
    zone: str
    bin1: str
    bin2: str
    reserve: str
    locked: str
    item_a: str
    item_b: str
    item_c: str

    # codes used when typing into selects
    @property
    def a(self) -> str:
        return f"A{self.u}"

    @property
    def b(self) -> str:
        return f"B{self.u}"

    def code(self, name: str) -> str:
        return f"{name}{self.u}"


def make_scenario(api: Api, u: str) -> Scenario:
    uoms = {x["code"]: x["id"] for x in api.get("/uoms")}
    ea, ctn = uoms["EA"], uoms["CTN"]

    def partner(code, ptype, active=True):
        p = api.post("/business-partners", {"code": f"{code}{u}", "name": f"{code} {u}", "partner_type": ptype})
        if not active:
            api.call("PUT", f"/business-partners/{p['id']}", {"is_active": False, "row_version": p["row_version"]})
        return p["id"]

    wh = api.post("/locations", {"code": f"WH{u}", "name": f"Warehouse {u}", "location_type": "WAREHOUSE"})["id"]

    def loc(code, ltype, parent=wh, pickable=False):
        return api.post("/locations", {
            "code": f"{code}{u}", "name": code, "location_type": ltype, "parent_id": parent, "is_pickable": pickable,
        })["id"]

    zone = loc("Z", "ZONE")
    locked = loc("BL", "BIN", zone)
    row = api.get(f"/locations/{locked}")
    api.call("PUT", f"/locations/{locked}", {"is_locked": True, "row_version": row["row_version"]})

    def item(code, **flags):
        return api.post("/items", {"sku_code": f"{code}{u}", "name": f"Item {code} {u}", "base_uom_id": ea, **flags})["id"]

    item_a = item("A")
    add_conversion(item_a, ctn, ea, 12)
    item_c = item("C")
    row = api.get(f"/items/{item_c}")
    api.call("PUT", f"/items/{item_c}", {"is_active": False, "row_version": row["row_version"]})

    return Scenario(
        u=u, ea=ea, ctn=ctn,
        supplier=partner("S", "supplier"), supplier_code=f"S{u}",
        inactive_supplier=partner("SX", "supplier", active=False),
        customer=partner("C", "customer"), customer_code=f"C{u}",
        customer2=partner("CB", "customer"),
        warehouse=wh, dock_in=loc("IN", "DOCK"), stage=loc("ST", "DOCK"), zone=zone,
        bin1=loc("BA", "BIN", zone, pickable=True), bin2=loc("BB", "BIN", zone, pickable=True),
        reserve=loc("BR", "BIN", zone, pickable=False), locked=locked,
        item_a=item_a, item_b=item("B", is_batch_managed=True, is_expiry_managed=True), item_c=item_c,
    )


def stock(api: Api, item_id: str) -> dict[tuple[str, str | None], tuple[float, float]]:
    """{(location code, batch): (on hand, allocated)} with zero rows left out"""
    out: dict = {}
    for r in api.get("/stock/balances", item_id=item_id, limit=500):
        on, al = float(r["qty_on_hand"]), float(r["qty_allocated"])
        if on or al:
            key = (r["location"]["code"], r["batch_no"])
            prev = out.get(key, (0.0, 0.0))
            out[key] = (prev[0] + on, prev[1] + al)
    return out


def ledger_totals(api: Api, item_id: str) -> dict[tuple[str, str | None], float]:
    out: dict = {}
    for r in api.get("/stock/ledger", item_id=item_id, limit=500):
        key = (r["location"]["code"], r["batch_no"])
        out[key] = out.get(key, 0.0) + float(r["qty_change"])
    return {k: v for k, v in out.items() if v}


# ---- API shortcuts for setting up preconditions (the UI path is tested in batch 1) -----------------------------

def po(api: Api, s: Scenario, lines: list[tuple[str, float]], confirm: bool = True, uom: str | None = None) -> dict:
    doc = api.post("/purchase-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": i, "uom_id": uom or s.ea, "qty": q} for i, q in lines
    ]})
    if confirm:
        doc = api.post(f"/purchase-orders/{doc['id']}/confirm")
    return doc


def received(api: Api, s: Scenario, item_id: str, qty: float, batch: str | None = None,
             expiry: datetime.date | None = None, location: str | None = None) -> dict:
    order = po(api, s, [(item_id, qty)])
    line = {"po_line_id": order["lines"][0]["id"], "qty": qty}
    if batch:
        line["batch_no"] = batch
    if expiry:
        line["expiry_date"] = expiry.isoformat()
    grn = api.post("/grns", {"po_id": order["id"], "location_id": location or s.dock_in, "lines": [line]})
    return api.post(f"/grns/{grn['id']}/post")


def in_bin(api: Api, s: Scenario, item_id: str, qty: float, bin_id: str, batch: str | None = None,
           expiry: datetime.date | None = None) -> None:
    received(api, s, item_id, qty, batch, expiry)
    pa = api.post("/putaways", {"lines": [{
        "item_id": item_id, "uom_id": s.ea, "qty": qty, "batch_no": batch,
        "expiry_date": expiry.isoformat() if expiry else None,
        "from_location_id": s.dock_in, "to_location_id": bin_id,
    }]})
    api.post(f"/putaways/{pa['id']}/post")


def so(api: Api, s: Scenario, lines: list[tuple[str, float]], confirm: bool = True, customer: str | None = None) -> dict:
    doc = api.post("/sales-orders", {"partner_id": customer or s.customer, "lines": [
        {"item_id": i, "uom_id": s.ea, "qty": q} for i, q in lines
    ]})
    if confirm:
        doc = api.post(f"/sales-orders/{doc['id']}/confirm")
    return doc
