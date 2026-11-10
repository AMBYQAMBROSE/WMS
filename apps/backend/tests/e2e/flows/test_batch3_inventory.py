"""Batch 3 - checklist E: stock enquiry, moves, adjustments, cycle counts, location lock."""

import datetime

from playwright.sync_api import expect

from tests.e2e.flows.kit import TODAY, in_bin, make_scenario, so, stock


def _reason(api, category: str, code: str) -> str:
    return next(r["id"] for r in api.get("/reason-codes", category=category) if r["code"] == code)


def _user(api, unique: str, role: str) -> tuple[str, str]:
    username, password = f"{role.lower()[:3]}{unique}".lower(), "Flow@Test123"
    api.post("/users", {"username": username, "display_name": f"{role.title()} {unique}", "password": password,
                        "role_codes": [role]})
    return username, password


def test_e_stock_and_moves(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    exp = TODAY + datetime.timedelta(days=45)
    in_bin(api, s, s.item_a, 50, s.bin1)
    in_bin(api, s, s.item_b, 20, s.bin2, batch=f"E1-{unique}", expiry=exp)
    flow.sign_in()

    flow.step("E-01  Stock enquiry filtered by item: on hand, batch, expiry")
    flow.goto("/stock")
    flow.choose(page.get_by_label("Filter by item"), s.b)
    flow.visible(page.locator("tr.ant-table-row", has_text=f"E1-{unique}"), "B batch row in stock enquiry")
    row = page.locator("tr.ant-table-row", has_text=f"E1-{unique}").first
    flow.check(exp.isoformat() in row.inner_text(), f"expiry shown in the stock row ({row.inner_text()[:120]!r})")
    flow.check("20" in row.inner_text(), "on-hand 20 shown")

    flow.step("E-02  Stock ledger for the item")
    ledger = api.get("/stock/ledger", item_id=s.item_b, limit=50)
    flow.check({r["movement_type"] for r in ledger} >= {"RECEIVE", "PUTAWAY_OUT", "PUTAWAY_IN"},
               f"ledger movement types {sorted({r['movement_type'] for r in ledger})}")
    flow.check(all(r["ref_line"] and r["ref_line"]["document"]["doc_no"] for r in ledger), "ledger rows link to documents")

    flow.step("E-03  Move A 10 from bin BA to bin BB in the web console")
    flow.goto("/moves/new")
    row = page.locator(".ant-table-tbody tr.ant-table-row").nth(0)
    flow.choose(row.locator(".ant-select").nth(0), s.a)
    row.locator(".ant-input-number input").fill("10")
    flow.choose(row.locator(".ant-select").nth(2), s.code("BA"))
    flow.choose(row.locator(".ant-select").last, s.code("BB"))
    page.get_by_role("button", name="Create move").click()
    mv = flow.saved("moves", lambda: api.post("/moves", {"lines": [{
        "item_id": s.item_a, "uom_id": s.ea, "qty": 10, "from_location_id": s.bin1, "to_location_id": s.bin2}]}),
        "Create move")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("moves", mv, "POSTED"), "POSTED", "move status")
    st = stock(api, s.item_a)
    flow.equal((st.get((s.code("BA"), None)), st.get((s.code("BB"), None))), ((40.0, 0.0), (10.0, 0.0)), "A after move")
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=s.item_a, limit=100)}
    flow.check({"MOVE_OUT", "MOVE_IN"} <= types, "MOVE_OUT / MOVE_IN ledger rows")

    flow.step("E-04  Moving allocated stock is refused")
    order = so(api, s, [(s.item_a, 40)])
    api.post(f"/sales-orders/{order['id']}/allocate", {"staging_location_id": s.stage})
    mv2 = api.post("/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 5,
                                         "from_location_id": s.bin1, "to_location_id": s.reserve}]})
    flow.rejected("POST", f"/moves/{mv2['id']}/post", None, "allocated", "move allocated stock")

    flow.step("E-05  Move to the same location is refused")
    flow.rejected("POST", "/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                  "from_location_id": s.bin2, "to_location_id": s.bin2}]}, "cannot be the same", "move to same bin")

    flow.step("E-21  Locked bin: no movement in or out, not allocated from")
    flow.rejected("POST", "/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                  "from_location_id": s.bin2, "to_location_id": s.locked}]}, "locked", "move into locked bin")


def test_e_adjustments(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 30, s.bin1)
    damage, found = _reason(api, "ADJUST", "DAMAGE"), _reason(api, "ADJUST", "FOUND")
    clerk = _user(api, unique, "CLERK")

    flow.step("E-10  Clerk creates an adjustment (-5 damaged) but cannot post it")
    flow.sign_in(*clerk)
    flow.goto("/adjustments/new")
    flow.choose("Adjustment reason", "Damaged")
    row = page.locator(".ant-table-tbody tr.ant-table-row").nth(0)
    flow.choose(row.locator(".ant-select").nth(0), s.code("BA"))
    flow.choose(row.locator(".ant-select").nth(1), s.a)
    row.get_by_text("Decrease").click()
    row.locator(".ant-input-number input").fill("5")
    page.get_by_role("button", name="Create adjustment").or_(page.get_by_role("button", name="Save")).first.click()
    adj = flow.saved("adjustments", lambda: api.post("/adjustments", {"reason_code_id": damage, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "location_id": s.bin1, "qty": -5}]}), "Clerk creates adjustment")
    flow.check(page.get_by_role("button", name="Post", exact=True).count() == 0, "clerk sees no Post button")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (30.0, 0.0), "stock unchanged by a draft adjustment")

    flow.step("E-10  Supervisor posts it; E-06 ledger shows the reason")
    flow.sign_out()
    flow.sign_in()
    flow.goto(f"/adjustments/{adj}")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("adjustments", adj, "POSTED"), "POSTED", "adjustment status")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (25.0, 0.0), "A after -5")
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=s.item_a, limit=100)}
    flow.check("ADJUST_OUT" in types, "ADJUST_OUT ledger row")

    flow.step("E-06  Increase +3 (found)")
    inc = api.post("/adjustments", {"reason_code_id": found, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "location_id": s.bin1, "qty": 3}]})
    api.post(f"/adjustments/{inc['id']}/post")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (28.0, 0.0), "A after +3")

    flow.step("E-07/E-08/E-09  Qty 0, below zero, no reason")
    flow.rejected("POST", "/adjustments", {"reason_code_id": damage, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "location_id": s.bin1, "qty": 0}]}, "cannot be 0", "adjustment qty 0")
    big = api.post("/adjustments", {"reason_code_id": damage, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "location_id": s.bin1, "qty": -100}]})
    flow.goto(f"/adjustments/{big['id']}")
    flow.confirm_action("Post")
    flow.expect_rejected("Insufficient stock", "adjust out 100 of 28")
    flow.rejected("POST", "/adjustments", {"lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "location_id": s.bin1, "qty": 1}]}, "", "adjustment without reason")


def test_e_cycle_count(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    exp = TODAY + datetime.timedelta(days=45)
    in_bin(api, s, s.item_a, 100, s.bin1)
    in_bin(api, s, s.item_b, 10, s.bin2, batch=f"C1-{unique}", expiry=exp)
    flow.sign_in()

    flow.step("E-12  A ZONE cannot be counted")
    flow.rejected("POST", "/cycle-counts", {"location_ids": [s.zone]}, "", "count a ZONE")

    flow.step("E-11  Start a count on BA and BB in the web console")
    flow.goto("/cycle-counts/new")
    flow.choose("Locations to count", s.code("BA"))
    flow.choose("Locations to count", s.code("BB"))
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Start count").or_(page.get_by_role("button", name="Start cycle count")).first.click()
    cc = flow.saved("cycle-counts", lambda: api.post("/cycle-counts", {"location_ids": [s.bin1, s.bin2]}), "Start count")
    flow.equal(api.get(f"/cycle-counts/{cc}")["status"], "COUNTING", "count status")

    flow.step("E-11  Frozen bins: receive / move / allocate are refused while counting")
    flow.rejected("POST", "/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                  "from_location_id": s.bin1, "to_location_id": s.reserve}]}, "being counted", "move out of counted bin")
    order = so(api, s, [(s.item_a, 5)])
    flow.rejected("POST", f"/sales-orders/{order['id']}/allocate", {"staging_location_id": s.stage}, "",
                  "allocate from counted bin only")

    flow.step("E-13  The same bin cannot be in two counts")
    flow.rejected("POST", "/cycle-counts", {"location_ids": [s.bin1]}, "already in cycle count", "overlapping count")

    flow.step("E-16  Posting with lines not counted is refused")
    flow.confirm_action("Post count")
    flow.expect_rejected("not counted", "post with uncounted lines")

    flow.step("E-19  Count A 98 (book 100) and B 10 in the web console")
    a_input = page.get_by_label(f"Counted quantity for {s.a} at {s.code('BA')}")
    a_input.fill("98")
    a_input.press("Enter")
    b_input = page.get_by_label(f"Counted quantity for {s.b} at {s.code('BB')}")
    b_input.fill("10")
    b_input.press("Enter")
    flow.visible(page.get_by_text("-2"), "difference -2 shown for A")

    flow.step("E-19  Found an item that is not on the books: A 4 in BB")
    found = page.locator(".ant-card", has_text="Items found that are not on the books")
    flow.choose(found.locator(".ant-select").nth(0), s.code("BB"))
    flow.choose(found.locator(".ant-select").nth(1), s.a)
    found.locator(".ant-input-number input").fill("4")
    found.get_by_role("button").last.click()
    page.wait_for_timeout(1500)
    lines = api.get(f"/cycle-counts/{cc}")["lines"]
    flow.check(len(lines) == 3, f"found item added as a count line ({len(lines)} lines)")

    flow.step("E-18  Recount the A line, enter 98 again")
    a_line = next((l for l in lines if l["item"]["sku_code"] == s.a and l["to_location"]["code"] == s.code("BA")), None)
    if a_line:
        api.post(f"/cycle-counts/{cc}/recount", {"line_ids": [a_line["id"]]})
        api.post(f"/cycle-counts/{cc}/counts", {"location_id": s.bin1, "item_id": s.item_a, "qty": 98})

    flow.step("E-19  Post the count: gain / loss written to stock, bins unfrozen")
    flow.goto(f"/cycle-counts/{cc}")
    flow.confirm_action("Post count")
    flow.equal(flow.wait_status("cycle-counts", cc, "POSTED"), "POSTED", "count status after post")
    st = stock(api, s.item_a)
    flow.equal((st.get((s.code("BA"), None)), st.get((s.code("BB"), None))), ((98.0, 0.0), (4.0, 0.0)),
               "A after count (-2 in BA, +4 found in BB)")
    types = {r["movement_type"] for r in api.get("/stock/ledger", item_id=s.item_a, limit=100)}
    flow.check({"COUNT_LOSS", "COUNT_GAIN"} <= types, "COUNT_LOSS / COUNT_GAIN ledger rows")
    mv = api.post("/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 1,
                                        "from_location_id": s.bin1, "to_location_id": s.reserve}]})
    r = api.client.post(f"/api/v1/moves/{mv['id']}/post", headers=api.headers)
    flow.check(r.is_success, f"bin unfrozen after posting the count ({r.status_code} {r.text[:120]})")

    flow.step("E-14  A count cannot start on stock reserved by an open pick list")
    order = so(api, s, [(s.item_a, 5)])
    api.post(f"/sales-orders/{order['id']}/allocate", {"staging_location_id": s.stage})
    flow.rejected("POST", "/cycle-counts", {"location_ids": [s.bin1]}, "reserved by pick lists", "count reserved stock")

    flow.step("E-17  Book stock not counted must be entered (0 if nothing)")
    cc2 = api.post("/cycle-counts", {"location_ids": [s.bin2]})
    for line in cc2["lines"]:
        if line["item"]["sku_code"] == s.b:
            api.post(f"/cycle-counts/{cc2['id']}/counts", {"location_id": s.bin2, "item_id": s.item_b, "qty": 10,
                                                            "batch_no": line["batch_no"], "expiry_date": line["expiry_date"]})
    flow.rejected("POST", f"/cycle-counts/{cc2['id']}/post", None, "not counted", "post with an uncounted book line")

    flow.step("E-20  Cancel the count: bins unfrozen, stock unchanged")
    flow.goto(f"/cycle-counts/{cc2['id']}")
    before = stock(api, s.item_b)
    flow.confirm_action("Cancel count")
    flow.equal(flow.wait_status("cycle-counts", cc2["id"], "CANCELLED"), "CANCELLED", "count status after cancel")
    flow.equal(stock(api, s.item_b), before, "B unchanged after cancel")


def test_e_blind_count(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 7, s.bin1)
    cc = api.post("/cycle-counts", {"location_ids": [s.bin1]})
    clerk = _user(api, unique, "CLERK")

    flow.step("E-15  Blind count: clerk (no view_expected) does not see book quantities")
    flow.sign_in(*clerk)
    flow.goto(f"/cycle-counts/{cc['id']}")
    flow.check(page.get_by_role("columnheader", name="Book qty").count() == 0, "Book qty column hidden for clerk")
    r = api.client.post("/api/v1/auth/login", data={"username": clerk[0], "password": clerk[1]})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    lines = api.client.get(f"/api/v1/cycle-counts/{cc['id']}", headers=headers).json()["lines"]
    flow.check(all(l["qty_planned"] is None for l in lines), "API hides book qty from clerk")
    inp = page.get_by_label(f"Counted quantity for {s.a} at {s.code('BA')}")
    inp.fill("7")
    inp.press("Enter")
    expect(page.get_by_text("To count")).to_have_count(0, timeout=10_000)
    api.post(f"/cycle-counts/{cc['id']}/cancel")
