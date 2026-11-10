"""Batch 5 - checklist J: extension modules (returns, cross-dock, repack, returnable assets)."""

import pytest

from tests.e2e.flows.kit import in_bin, make_scenario, po, received, so, stock

FEATURES = ("RETURNS", "CROSS_DOCK", "REPACK", "RETURNABLE_ASSET")


@pytest.fixture
def features(flow):
    def set_all(on: bool):
        for code in FEATURES:
            flow.api.call("PUT", f"/features/{code}", {"enabled": on})

    set_all(True)
    yield set_all
    set_all(False)


def _reason(api, category, code):
    return next(r["id"] for r in api.get("/reason-codes", category=category) if r["code"] == code)


def _shipped(api, s, item, qty):
    """SO for `qty` of `item`, picked and shipped in full"""
    o = so(api, s, [(item, qty)])
    api.post(f"/sales-orders/{o['id']}/allocate", {"staging_location_id": s.stage})
    pick = [p for p in api.get("/picks", so_id=o["id"]) if p["status"] == "OPEN"][0]
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    ship = api.post("/shipments", {"so_id": o["id"]})
    api.post(f"/shipments/{ship['id']}/post")
    return api.get(f"/sales-orders/{o['id']}")


def test_j_returns(flow, unique, features):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 20, s.bin1)
    order = _shipped(api, s, s.item_a, 10)
    damaged = _reason(api, "RETURN", "DAMAGED")
    flow.sign_in()

    flow.step("J-01  Customer return started from the shipped order (web)")
    flow.goto(f"/sales-orders/{order['id']}")
    page.get_by_role("button", name="Customer return").click()
    page.wait_for_url("**/returns-in/new?so=*")
    flow.loaded()
    flow.visible(page.get_by_text(s.a), "order lines prefilled on the return form")

    flow.step("J-01  Post a return: 3 restocked to BB, 2 scrapped")
    line = order["lines"][0]
    ret = api.post("/returns-in", {"partner_id": s.customer, "ref_document_id": order["id"], "reason_code_id": damaged,
                                   "lines": [
                                       {"item_id": s.item_a, "uom_id": s.ea, "qty": 3, "disposition": "RESTOCK",
                                        "location_id": s.bin2, "ref_line_id": line["id"]},
                                       {"item_id": s.item_a, "uom_id": s.ea, "qty": 2, "disposition": "SCRAP",
                                        "ref_line_id": line["id"]}]})
    flow.goto(f"/returns-in/{ret['id']}")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("returns-in", ret["id"], "POSTED"), "POSTED", "return status")
    flow.equal(stock(api, s.item_a).get((s.code("BB"), None)), (3.0, 0.0), "restocked qty in BB (scrap not stocked)")
    flow.equal(float(api.get(f"/sales-orders/{order['id']}")["lines"][0]["returned"]), 5.0, "SO line returned qty")

    flow.step("J-02  Return more than shipped (5 already returned of 10)")
    flow.rejected("POST", "/returns-in", {"partner_id": s.customer, "ref_document_id": order["id"],
                  "reason_code_id": damaged, "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 6,
                                                         "disposition": "SCRAP"}]},
                  "exceeds the returnable quantity", "return 6 more")

    flow.step("J-03  Wrong customer / item not on order / restock without location")
    flow.rejected("POST", "/returns-in", {"partner_id": s.customer2, "ref_document_id": order["id"],
                  "reason_code_id": damaged, "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                                                         "disposition": "SCRAP"}]}, "differs", "other customer")
    flow.rejected("POST", "/returns-in", {"partner_id": s.customer, "ref_document_id": order["id"],
                  "reason_code_id": damaged, "lines": [{"item_id": s.item_b, "uom_id": s.ea, "qty": 1,
                                                         "batch_no": "X", "expiry_date": "2030-01-01",
                                                         "disposition": "SCRAP"}]}, "is not on order", "item not on SO")
    flow.rejected("POST", "/returns-in", {"partner_id": s.customer, "ref_document_id": order["id"],
                  "reason_code_id": damaged, "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                                                         "disposition": "RESTOCK"}]}, "restock location", "no location")

    flow.step("J-04  Return to supplier from BA, linked to the PO")
    order_po = po(api, s, [(s.item_a, 5)])
    g = api.post("/grns", {"po_id": order_po["id"], "location_id": s.bin1,
                           "lines": [{"po_line_id": order_po["lines"][0]["id"], "qty": 5}]})
    api.post(f"/grns/{g['id']}/post")
    before = stock(api, s.item_a).get((s.code("BA"), None))[0]
    rout = api.post("/returns-out", {"partner_id": s.supplier, "ref_document_id": order_po["id"],
                                     "reason_code_id": _reason(api, "RETURN", "QUALITY"),
                                     "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 2, "location_id": s.bin1}]})
    flow.goto(f"/returns-out/{rout['id']}")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("returns-out", rout["id"], "POSTED"), "POSTED", "return to supplier status")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None))[0], before - 2, "BA after return to supplier")

    flow.step("J-05  Return allocated stock to the supplier")
    hold = so(api, s, [(s.item_a, before - 2)])
    api.post(f"/sales-orders/{hold['id']}/allocate", {"staging_location_id": s.stage})
    r2 = api.post("/returns-out", {"partner_id": s.supplier, "reason_code_id": _reason(api, "RETURN", "QUALITY"),
                                   "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1, "location_id": s.bin1}]})
    flow.rejected("POST", f"/returns-out/{r2['id']}/post", None, "allocated", "return allocated stock")

    flow.step("J-06  With RETURNS off the menu is hidden and the API refuses")
    api.call("PUT", "/features/RETURNS", {"enabled": False})
    flow.goto(f"/sales-orders/{order['id']}")
    flow.check(page.get_by_role("button", name="Customer return").count() == 0, "Customer return button hidden")
    flow.rejected("GET", "/returns-in", None, "", "returns API with feature off")


def test_j_cross_dock_repack_assets(flow, unique, features):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    flow.sign_in()

    flow.step("J-07  Cross-dock: allocate straight from the receiving dock (web)")
    received(api, s, s.item_a, 12)
    o = so(api, s, [(s.item_a, 12)])
    flow.goto(f"/sales-orders/{o['id']}")
    page.get_by_role("button", name="Allocate stock").click()
    dialog = page.get_by_role("dialog")
    flow.choose(dialog.locator(".ant-select").first, s.code("ST"))
    dialog.get_by_text("Cross-dock").click()
    flow.choose(dialog.locator(".ant-select").nth(1), s.code("IN"))
    dialog.get_by_role("button", name="Allocate").click()
    page.wait_for_timeout(1500)
    picks = api.get("/picks", so_id=o["id"])
    if flow.check(len(picks) == 1, "pick list created by cross-dock allocation"):
        lines = api.get(f"/picks/{picks[0]['id']}")["lines"]
        flow.equal({l["from_location"]["code"] for l in lines}, {s.code("IN")}, "cross-dock pick source")

    flow.step("J-08  Cross-dock source = staging")
    o2 = so(api, s, [(s.item_a, 1)])
    flow.rejected("POST", f"/sales-orders/{o2['id']}/allocate",
                  {"staging_location_id": s.stage, "source_location_id": s.stage}, "cannot be the same", "source = staging")

    flow.step("J-09  Repack: consume 1 CTN of A, produce 12 EA of B")
    in_bin(api, s, s.item_a, 12, s.bin1)
    rp = api.post("/repacks", {
        "inputs": [{"item_id": s.item_a, "uom_id": s.ctn, "qty": 1, "location_id": s.bin1}],
        "outputs": [{"item_id": s.item_b, "uom_id": s.ea, "qty": 12, "batch_no": f"RP{unique}",
                     "expiry_date": "2030-01-01", "location_id": s.bin2}]})
    flow.goto(f"/repacks/{rp['id']}")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("repacks", rp["id"], "POSTED"), "POSTED", "repack status")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), None, "A consumed (12 EA = 1 CTN)")
    flow.equal(stock(api, s.item_b).get((s.code("BB"), f"RP{unique}")), (12.0, 0.0), "B produced")

    flow.step("J-10  Repack consuming more than available: nothing happens")
    rp2 = api.post("/repacks", {
        "inputs": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 999, "location_id": s.bin1}],
        "outputs": [{"item_id": s.item_b, "uom_id": s.ea, "qty": 1, "batch_no": f"RP{unique}",
                     "expiry_date": "2030-01-01", "location_id": s.bin2}]})
    flow.rejected("POST", f"/repacks/{rp2['id']}/post", None, "Insufficient stock", "repack 999")
    flow.equal(stock(api, s.item_b).get((s.code("BB"), f"RP{unique}")), (12.0, 0.0), "B unchanged after failed repack")

    flow.step("J-11  Returnable assets: lend 10 pallets, 4 come back (web)")
    pallet = api.post("/returnable-assets/types", {"code": f"PAL{unique}", "name": f"Pallet {unique}"})
    flow.goto("/returnable-assets")
    page.get_by_role("button", name="Record issue").or_(page.get_by_role("button", name="Issue")).first.click()
    dialog = page.get_by_role("dialog")
    flow.choose(dialog.get_by_label("Partner"), s.customer_code)
    dialog.get_by_text(f"Pallet {unique}").click()
    dialog.get_by_label("Quantity").fill("10")
    dialog.get_by_role("button", name="OK").or_(dialog.get_by_role("button", name="Save")).first.click()
    page.wait_for_timeout(1500)
    api.post("/returnable-assets/transactions", {"partner_id": s.customer, "asset_type_id": pallet["id"],
                                                 "txn_type": "RETURN", "qty": 4})
    txns = api.get("/returnable-assets/transactions", partner_id=s.customer, asset_type_id=pallet["id"])
    flow.equal(sum(float(t["qty_change"]) for t in txns), 6.0, "outstanding pallets (10 issued via web, 4 returned)")

    flow.step("J-12  Return more than outstanding")
    flow.rejected("POST", "/returnable-assets/transactions", {"partner_id": s.customer, "asset_type_id": pallet["id"],
                  "txn_type": "RETURN", "qty": 7}, "outstanding", "return 7 of 6")
    flow.goto("/returnable-assets")
    page.wait_for_timeout(1000)
