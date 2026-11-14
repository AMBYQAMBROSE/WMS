"""Batch 2 - checklist B (purchase orders), C (receiving) and D (putaway): rules and negative cases."""

import base64
import datetime

from playwright.sync_api import expect

from tests.e2e.flows.kit import TODAY, make_scenario, po, received, stock

PNG_1PX = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)).decode()


def _feature(api, code: str, on: bool) -> None:
    api.call("PUT", f"/features/{code}", {"enabled": on})


# ===================================================================================== B. purchase orders

def test_b_purchase_orders(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    flow.sign_in()

    flow.step("B-02  Save an empty purchase order: required-field messages")
    flow.goto("/purchase-orders/new")
    page.get_by_role("button", name="Save", exact=True).click()
    errors = page.locator(".ant-form-item-explain-error")
    expect(errors.first).to_be_visible()
    texts = errors.all_inner_texts()
    flow.check(any("Supplier" in t or "required" in t.lower() for t in texts), f"supplier required message ({texts})")
    flow.check(any("item" in t.lower() for t in texts), f"item required message ({texts})")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.supplier, "lines": []}, "", "PO with no lines")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "qty": 0}]}, "", "PO line qty 0")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "qty": -5}]}, "", "PO line negative qty")

    flow.step("B-03/B-04/B-05  Inactive supplier, customer as supplier, inactive item")
    # The inactive supplier must not be offered: type its code and expect no matching option
    page.get_by_label("Supplier", exact=True).click()
    page.keyboard.type(f"SX{unique}", delay=20)
    page.wait_for_timeout(2500)
    offered = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option", has_text=f"SX{unique}")
    flow.check(offered.count() == 0, "inactive supplier selectable in the dropdown")
    page.keyboard.press("Escape")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.inactive_supplier, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "qty": 1}]}, "inactive", "PO for inactive supplier")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.customer, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "qty": 1}]}, "is not a supplier", "PO for a customer")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": s.item_c, "uom_id": s.ea, "qty": 1}]}, "inactive", "PO with inactive item")

    flow.step("B-06  Line in a unit the item has no conversion for (B in CTN)")
    flow.goto("/purchase-orders/new")
    flow.choose("Supplier", s.supplier_code)
    row = page.locator(".wms-lines-row").nth(0)
    flow.choose_in(row, s.b)
    # The unit dropdown offers only the item's base unit and packing units, so CTN is not there for B
    row.locator(".ant-select").nth(1).click()
    offered = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option")
    expect(offered.first).to_be_visible()
    flow.check(not any("CTN" in t for t in offered.all_inner_texts()), "CTN not offered for B, which has no carton packing")
    page.keyboard.press("Escape")
    flow.rejected("POST", "/purchase-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": s.item_b, "uom_id": s.ctn, "qty": 2}]}, "no conversion", "PO line B in CTN")

    flow.step("B-01/B-07  Create a draft and edit it (change qty, add a line)")
    flow.goto("/purchase-orders/new")
    flow.choose("Supplier", s.supplier_code)
    flow.choose_in(page.locator(".wms-lines-row").nth(0), s.a)
    page.get_by_label("Quantity, line 1").fill("10")
    page.get_by_role("button", name="Save", exact=True).click()
    po_id = flow.wait_doc("purchase-orders")
    page.get_by_role("button", name="Edit", exact=True).click()
    page.wait_for_url("**/edit")
    flow.loaded()
    page.get_by_label("Quantity, line 1").fill("12")
    page.get_by_role("button", name="Add line").click()
    flow.choose_in(page.locator(".wms-lines-row").nth(1), s.b)
    page.get_by_label("Quantity, line 2").fill("8")
    page.get_by_role("button", name="Save", exact=True).click()
    flow.wait_doc("purchase-orders")
    doc = api.get(f"/purchase-orders/{po_id}")
    flow.equal([float(l["qty_planned"]) for l in doc["lines"]], [12.0, 8.0], "PO lines after edit")

    flow.step("B-09/B-08  Confirm; editing is no longer possible")
    flow.confirm_action("Confirm")
    flow.wait_status("purchase-orders", po_id, "CONFIRMED")
    flow.check(page.get_by_role("button", name="Edit", exact=True).count() == 0, "Edit button hidden after confirm")
    flow.goto(f"/purchase-orders/{po_id}/edit")
    flow.visible(page.get_by_text("no longer a draft"), "edit page of a confirmed PO warns it is not a draft")
    doc = api.get(f"/purchase-orders/{po_id}")
    flow.rejected("PUT", f"/purchase-orders/{po_id}", {"partner_id": s.supplier, "row_version": doc["row_version"],
                  "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1}]}, "CONFIRMED", "edit confirmed PO via API")

    flow.step("B-10  Cancel a confirmed PO without receipts")
    flow.goto(f"/purchase-orders/{po_id}")
    flow.confirm_action("Cancel")
    flow.equal(flow.wait_status("purchase-orders", po_id, "CANCELLED"), "CANCELLED", "PO status after cancel")
    flow.check(page.get_by_role("button", name="Receive").count() == 0, "Receive button hidden on cancelled PO")
    flow.rejected("POST", f"/purchase-orders/{po_id}/confirm", None, "CANCELLED", "confirm a cancelled PO")

    flow.step("B-11  Close a partially received PO; B-14 progress shown")
    order = po(api, s, [(s.item_a, 10)])
    grn = api.post("/grns", {"po_id": order["id"], "location_id": s.dock_in,
                             "lines": [{"po_line_id": order["lines"][0]["id"], "qty": 4}]})
    api.post(f"/grns/{grn['id']}/post")
    flow.goto(f"/purchase-orders/{order['id']}")
    flow.visible(page.get_by_text(grn["doc_no"]), "receipt listed on the PO")
    flow.confirm_action("Close")
    flow.equal(flow.wait_status("purchase-orders", order["id"], "CLOSED"), "CLOSED", "PO status after close")
    flow.equal(stock(api, s.item_a).get((s.code("IN"), None)), (4.0, 0.0), "received stock stays after close")
    flow.rejected("POST", f"/purchase-orders/{order['id']}/cancel", None, "CLOSED", "cancel a closed PO")

    flow.step("B-12  Cancel a fully received PO")
    full = po(api, s, [(s.item_a, 3)])
    g = api.post("/grns", {"po_id": full["id"], "location_id": s.dock_in,
                           "lines": [{"po_line_id": full["lines"][0]["id"], "qty": 3}]})
    api.post(f"/grns/{g['id']}/post")
    flow.rejected("POST", f"/purchase-orders/{full['id']}/cancel", None, "RECEIVED", "cancel a received PO")

    flow.step("B-13  List: search by number and filter by status")
    flow.goto("/purchase-orders")
    page.get_by_placeholder("Search number, partner, remark…").fill(order["doc_no"])
    flow.attempt("search by doc no shows exactly one row", lambda: expect(page.locator(".ant-table-tbody tr.ant-table-row")).to_have_count(1, timeout=30_000))
    page.get_by_placeholder("Search number, partner, remark…").fill(s.supplier_code)
    page.wait_for_timeout(6000)
    flow.check(page.locator(".ant-table-tbody tr.ant-table-row").count() >= 3, "search by supplier code finds its POs")


# ===================================================================================== C. receiving

def test_c_receiving(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    flow.sign_in()

    flow.step("C-01/C-02  Receiving from draft / cancelled / closed POs is refused")
    draft = po(api, s, [(s.item_a, 5)], confirm=False)
    body = lambda o: {"po_id": o["id"], "location_id": s.dock_in, "lines": [{"po_line_id": o["lines"][0]["id"], "qty": 1}]}  # noqa: E731
    flow.rejected("POST", "/grns", body(draft), "DRAFT", "GRN for draft PO")
    flow.goto("/grns/new")
    page.locator("#grn-po").click()
    page.keyboard.type(draft["doc_no"])
    page.wait_for_timeout(500)
    flow.check(page.locator(".ant-select-item-option", has_text=draft["doc_no"]).count() == 0,
               "draft PO offered in the GRN purchase order dropdown")
    page.keyboard.press("Escape")
    cancelled = po(api, s, [(s.item_a, 5)])
    api.post(f"/purchase-orders/{cancelled['id']}/cancel")
    flow.rejected("POST", "/grns", body(cancelled), "CANCELLED", "GRN for cancelled PO")

    flow.step("C-06  GRN line from another PO")
    o1, o2 = po(api, s, [(s.item_a, 5)]), po(api, s, [(s.item_a, 5)])
    flow.rejected("POST", "/grns", {"po_id": o1["id"], "location_id": s.dock_in,
                  "lines": [{"po_line_id": o2["lines"][0]["id"], "qty": 1}]}, "does not belong", "line of another PO")

    flow.step("C-07  Over-receipt with the flag off (also across two GRNs)")
    _feature(api, "ALLOW_OVER_RECEIPT", False)
    over = po(api, s, [(s.item_a, 10)])
    line = over["lines"][0]["id"]
    flow.rejected("POST", "/grns", {"po_id": over["id"], "location_id": s.dock_in,
                  "lines": [{"po_line_id": line, "qty": 11}]}, "over-received", "receive 11 of 10")
    g1 = api.post("/grns", {"po_id": over["id"], "location_id": s.dock_in, "lines": [{"po_line_id": line, "qty": 8}]})
    api.post(f"/grns/{g1['id']}/post")
    flow.rejected("POST", "/grns", {"po_id": over["id"], "location_id": s.dock_in,
                  "lines": [{"po_line_id": line, "qty": 3}]}, "over-received", "receive 8 + 3 of 10")
    g2 = api.post("/grns", {"po_id": over["id"], "location_id": s.dock_in, "lines": [{"po_line_id": line, "qty": 2}]})
    api.post(f"/grns/{g2['id']}/post")
    flow.equal(api.get(f"/purchase-orders/{over['id']}")["status"], "RECEIVED", "8 + 2 of 10 -> RECEIVED")

    flow.step("C-08  Over-receipt with ALLOW_OVER_RECEIPT on")
    _feature(api, "ALLOW_OVER_RECEIPT", True)
    try:
        o = po(api, s, [(s.item_a, 10)])
        g = api.call("POST", "/grns", {"po_id": o["id"], "location_id": s.dock_in,
                                       "lines": [{"po_line_id": o["lines"][0]["id"], "qty": 12}]}, expect=None)
        api.post(f"/grns/{g['id']}/post")
        doc = api.get(f"/purchase-orders/{o['id']}")
        flow.equal(doc["status"], "RECEIVED", "PO status after over-receipt")
        flow.equal(float(doc["lines"][0]["qty_actual"]), 12.0, "received qty after over-receipt")
    except AssertionError as exc:
        flow.check(False, f"over-receipt with flag on: {exc}")
    finally:
        _feature(api, "ALLOW_OVER_RECEIPT", False)

    flow.step("C-09/C-10  Batch / expiry required for B")
    ob = po(api, s, [(s.item_b, 10)])
    bl = ob["lines"][0]["id"]
    flow.rejected("POST", "/grns", {"po_id": ob["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": bl, "qty": 1, "expiry_date": TODAY.isoformat()}]}, "batch number is required", "B without batch")
    flow.rejected("POST", "/grns", {"po_id": ob["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": bl, "qty": 1, "batch_no": "X1"}]}, "expiry date is required", "B without expiry")
    flow.goto(f"/grns/new?po={ob['id']}")
    flow.choose("Receiving location", s.code("IN"))
    page.get_by_role("button", name="Create goods receipt").click()
    flow.visible(page.locator(".ant-form-item-explain-error, .ant-input-status-error, .ant-picker-status-error"), "web form marks missing batch/expiry before submitting")

    flow.step("C-11  Plain item received with a batch typed in (API)")
    oa = po(api, s, [(s.item_a, 2)])
    g = api.post("/grns", {"po_id": oa["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": oa["lines"][0]["id"], "qty": 2, "batch_no": "SHOULD-DROP"}]})
    flow.equal(g["lines"][0]["batch_no"], None, "batch on a non-batch item is dropped")

    flow.step("C-12/C-13  Receive to a ZONE / a locked bin")
    flow.rejected("POST", "/grns", {"po_id": oa["id"], "location_id": s.zone, "lines": [
        {"po_line_id": oa["lines"][0]["id"], "qty": 1}]}, "only", "GRN to a ZONE")
    flow.rejected("POST", "/grns", {"po_id": oa["id"], "location_id": s.locked, "lines": [
        {"po_line_id": oa["lines"][0]["id"], "qty": 1}]}, "locked", "GRN to a locked bin")

    flow.step("C-14/C-15  Draft GRN has no effect; posting adds stock and ledger")
    before = stock(api, s.item_a).get((s.code("IN"), None), (0.0, 0.0))[0]
    flow.goto(f"/grns/{g['id']}")
    flow.equal(stock(api, s.item_a).get((s.code("IN"), None), (0.0, 0.0))[0], before, "stock while GRN is draft")
    flow.confirm_action("Post")
    flow.wait_status("grns", g["id"], "POSTED")
    flow.equal(stock(api, s.item_a).get((s.code("IN"), None))[0], before + 2, "stock after posting")
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=s.item_a, limit=500)}
    flow.check("RECEIVE" in types, "RECEIVE ledger rows exist")

    flow.step("C-16  Post the same GRN twice")
    flow.rejected("POST", f"/grns/{g['id']}/post", None, "POSTED", "second post")
    flow.equal(stock(api, s.item_a).get((s.code("IN"), None))[0], before + 2, "stock added only once")
    flow.check(page.get_by_role("button", name="Post", exact=True).count() == 0, "Post button gone after posting")

    flow.step("C-19  Cancel a posted GRN")
    flow.rejected("POST", f"/grns/{g['id']}/cancel", None, "POSTED", "cancel posted GRN")

    flow.step("C-17  PO closed while a GRN is still draft, then post the GRN")
    oc = po(api, s, [(s.item_a, 10)])
    first = api.post("/grns", {"po_id": oc["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": oc["lines"][0]["id"], "qty": 2}]})
    api.post(f"/grns/{first['id']}/post")
    pending = api.post("/grns", {"po_id": oc["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": oc["lines"][0]["id"], "qty": 3}]})
    api.post(f"/purchase-orders/{oc['id']}/close")
    flow.rejected("POST", f"/grns/{pending['id']}/post", None, "CLOSED", "post GRN of a closed PO")

    flow.step("C-18  Cancel a draft GRN in the web console")
    od = po(api, s, [(s.item_a, 4)])
    d = api.post("/grns", {"po_id": od["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": od["lines"][0]["id"], "qty": 4}]})
    flow.goto(f"/grns/{d['id']}")
    flow.confirm_action("Cancel")
    flow.equal(flow.wait_status("grns", d["id"], "CANCELLED"), "CANCELLED", "GRN status after cancel")
    flow.rejected("POST", f"/grns/{d['id']}/post", None, "CANCELLED", "post a cancelled GRN")

    flow.step("C-20  Photo on a receipt: PNG accepted, PDF / empty rejected")
    r = api.client.post(f"/api/v1/documents/{g['id']}/attachments", headers=api.headers,
                        json={"content_base64": PNG_1PX, "caption": "damaged carton"})
    flow.check(r.status_code == 201, f"PNG photo upload ({r.status_code} {r.text[:150]})")
    flow.rejected("POST", f"/documents/{g['id']}/attachments",
                  {"content_base64": base64.b64encode(b"%PDF-1.4 fake").decode()}, "photo", "PDF as photo")
    flow.rejected("POST", f"/documents/{g['id']}/attachments", {"content_base64": "!!!"}, "", "invalid base64")
    # Photos are behind the "Photos (n)" button next to the document number
    flow.goto(f"/grns/{g['id']}")
    flow.attempt("open the receipt's photos", page.get_by_role("button", name="Photos (1)").click, timeout=10_000)
    flow.visible(page.get_by_test_id("document-photos").locator("img"), "photo visible in the receipt's photos")
    page.keyboard.press("Escape")

    flow.step("C-21  Receiving into a location that is being counted")
    received(api, s, s.item_a, 1, location=s.bin2)
    count = api.post("/cycle-counts", {"location_ids": [s.bin2]})
    try:
        o = po(api, s, [(s.item_a, 1)])
        flow.rejected("POST", "/grns", {"po_id": o["id"], "location_id": s.bin2, "lines": [
            {"po_line_id": o["lines"][0]["id"], "qty": 1}]}, "being counted", "GRN into a counted bin")
    finally:
        api.post(f"/cycle-counts/{count['id']}/cancel")


# ===================================================================================== D. putaway

def test_d_putaway(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    exp = TODAY + datetime.timedelta(days=60)
    flow.sign_in()

    line = lambda qty, to, **kw: {"item_id": s.item_a, "uom_id": s.ea, "qty": qty,  # noqa: E731
                                  "from_location_id": kw.get("frm", s.dock_in), "to_location_id": to, **kw.get("extra", {})}

    flow.step("D-02  Putaway from a draft GRN: warning and disabled button")
    od = po(api, s, [(s.item_a, 5)])
    draft = api.post("/grns", {"po_id": od["id"], "location_id": s.dock_in, "lines": [
        {"po_line_id": od["lines"][0]["id"], "qty": 5}]})
    flow.goto(f"/putaways/new?grn={draft['id']}")
    flow.visible(page.get_by_text("not posted yet"), "warning for unposted GRN")
    flow.check(page.get_by_role("button", name="Create putaway").is_disabled(), "create button disabled")
    flow.rejected("POST", "/putaways", {"ref_document_id": draft["id"], "lines": [line(1, s.bin1)]},
                  "DRAFT", "putaway referencing a draft GRN")

    flow.step("D-03  Split one GRN line across two bins (60 -> 40 + 20)")
    g = received(api, s, s.item_a, 60)
    flow.goto(f"/grns/{g['id']}")
    page.get_by_role("button", name="Create putaway").click()
    page.wait_for_url("**/putaways/new?grn=*")
    flow.loaded()
    rows = page.locator(".ant-table-tbody tr.ant-table-row")
    rows.nth(0).locator(".ant-input-number input").fill("40")
    flow.choose(rows.nth(0).locator(".ant-select").last, s.code("BA"))
    page.get_by_label("Split line 1").click()
    rows.nth(1).locator(".ant-input-number input").fill("20")
    flow.choose(rows.nth(1).locator(".ant-select").last, s.code("BB"))
    page.get_by_role("button", name="Create putaway").click()
    pa = flow.saved("putaways", lambda: api.post("/putaways", {"ref_document_id": g["id"], "lines": [
        line(40, s.bin1), line(20, s.bin2)]}), "Create split putaway")
    flow.confirm_action("Post")
    flow.wait_status("putaways", pa, "POSTED")
    st = stock(api, s.item_a)
    flow.equal((st.get((s.code("BA"), None)), st.get((s.code("BB"), None)), st.get((s.code("IN"), None))),
               ((40.0, 0.0), (20.0, 0.0), None), "stock after split putaway")
    types = [r["movement_type"] for r in api.get("/stock/ledger", item_id=s.item_a, limit=500)]
    flow.check("PUTAWAY_OUT" in types and "PUTAWAY_IN" in types, "PUTAWAY_OUT / PUTAWAY_IN ledger rows")

    flow.step("D-13  Second putaway from the same, already put-away GRN")
    flow.goto(f"/grns/{g['id']}")
    page.get_by_role("button", name="Create putaway").click()
    page.wait_for_url("**/putaways/new?grn=*")
    flow.loaded()
    prefilled = page.locator(".ant-table-tbody tr.ant-table-row .ant-input-number input").evaluate_all(
        "els => els.map(e => e.value)")
    flow.check(prefilled in ([], ["0"], [""]),
               f"putaway form for a fully put-away GRN is prefilled with {prefilled} (should offer nothing left)")

    flow.step("D-04/D-05/D-08  Target a DOCK, same source/target, locked target")
    received(api, s, s.item_a, 10)
    flow.rejected("POST", "/putaways", {"lines": [line(1, s.stage)]}, "only", "putaway to a DOCK")
    flow.rejected("POST", "/putaways", {"lines": [line(1, s.dock_in)]}, "cannot be the same", "same source/target")
    flow.rejected("POST", "/putaways", {"lines": [line(1, s.locked)]}, "locked", "putaway to a locked bin")
    flow.rejected("POST", "/putaways", {"lines": [line(1, s.zone)]}, "only", "putaway to a ZONE")

    flow.step("D-06  Put away more than the dock holds: posting refused, nothing moves")
    big = api.post("/putaways", {"lines": [line(999, s.bin1)]})
    flow.goto(f"/putaways/{big['id']}")
    before = stock(api, s.item_a)
    flow.confirm_action("Post")
    flow.expect_rejected("Insufficient stock", "post putaway of 999")
    flow.equal(api.get(f"/putaways/{big['id']}")["status"], "DRAFT", "putaway stays draft")
    flow.equal(stock(api, s.item_a), before, "stock unchanged after refused post")

    flow.step("D-07  Wrong batch for B")
    received(api, s, s.item_b, 5, batch=f"OK{unique}", expiry=exp)
    wrong = api.post("/putaways", {"lines": [{"item_id": s.item_b, "uom_id": s.ea, "qty": 5, "batch_no": "NOPE",
                                              "expiry_date": exp.isoformat(), "from_location_id": s.dock_in,
                                              "to_location_id": s.bin2}]})
    flow.rejected("POST", f"/putaways/{wrong['id']}/post", None, "Insufficient stock", "post wrong batch")

    flow.step("D-10  Cancel a draft putaway in the UI; cancelling a posted one is refused")
    flow.goto(f"/putaways/{big['id']}")
    flow.confirm_action("Cancel")
    flow.equal(flow.wait_status("putaways", big["id"], "CANCELLED"), "CANCELLED", "putaway status after cancel")
    flow.rejected("POST", f"/putaways/{pa}/cancel", None, "POSTED", "cancel posted putaway")

    flow.step("D-12  Free putaway without a GRN, entered by hand")
    flow.goto("/putaways/new")
    row = page.locator(".ant-table-tbody tr.ant-table-row").nth(0)
    flow.choose(row.locator(".ant-select").nth(0), s.a)
    row.locator(".ant-input-number input").fill("10")
    flow.choose(row.locator(".ant-select").nth(2), s.code("IN"))
    flow.choose(row.locator(".ant-select").last, s.code("BR"))
    page.get_by_role("button", name="Create putaway").click()
    free = flow.saved("putaways", lambda: api.post("/putaways", {"lines": [line(10, s.reserve)]}), "Create free putaway")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("putaways", free, "POSTED"), "POSTED", "free putaway status")
    flow.equal(stock(api, s.item_a).get((s.code("BR"), None)), (10.0, 0.0), "reserve bin after free putaway")
