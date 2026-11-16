"""Batch 4 - checklist F (sales orders, allocation), G (picking), H (shipping), I (close / cancel)."""

import datetime
import threading


from tests.e2e.flows.kit import TODAY, in_bin, make_scenario, so, stock


def _alloc(api, order_id, staging):
    return api.client.post(f"/api/v1/sales-orders/{order_id}/allocate", headers=api.headers,
                           json={"staging_location_id": staging})


def _pick_lines(api, order_id):
    picks = [p for p in api.get("/picks", so_id=order_id) if p["status"] == "OPEN"]
    return (picks[0], api.get(f"/picks/{picks[0]['id']}")["lines"]) if picks else (None, [])


def test_f_allocation_rules(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    flow.sign_in()

    flow.step("F-02  Sales order for an inactive item / a supplier as customer")
    flow.rejected("POST", "/sales-orders", {"partner_id": s.customer, "lines": [
        {"item_id": s.item_c, "uom_id": s.ea, "qty": 1}]}, "inactive", "SO with inactive item")
    flow.rejected("POST", "/sales-orders", {"partner_id": s.supplier, "lines": [
        {"item_id": s.item_a, "uom_id": s.ea, "qty": 1}]}, "is not a customer", "SO for a supplier")

    flow.step("F-04  Allocate a draft order")
    draft = so(api, s, [(s.item_a, 1)], confirm=False)
    flow.rejected("POST", f"/sales-orders/{draft['id']}/allocate", {"staging_location_id": s.stage}, "DRAFT",
                  "allocate a draft SO")
    flow.goto(f"/sales-orders/{draft['id']}")
    flow.check(page.get_by_role("button", name="Allocate stock").count() == 0, "Allocate hidden on a draft SO")

    flow.step("F-03  Edit a confirmed sales order")
    conf = so(api, s, [(s.item_a, 1)])
    flow.rejected("PUT", f"/sales-orders/{conf['id']}", {"partner_id": s.customer, "row_version": conf["row_version"],
                  "lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 2}]}, "CONFIRMED", "edit a confirmed SO")

    flow.step("F-05/F-06/F-07/F-08  FEFO, pickable bins first, expired excluded")
    b_early, b_late, b_old = f"EARLY{unique}", f"LATE{unique}", f"EXP{unique}"
    in_bin(api, s, s.item_b, 5, s.reserve, batch=b_early, expiry=TODAY + datetime.timedelta(days=10))
    in_bin(api, s, s.item_b, 5, s.bin1, batch=b_late, expiry=TODAY + datetime.timedelta(days=200))
    in_bin(api, s, s.item_b, 5, s.bin2, batch=b_early, expiry=TODAY + datetime.timedelta(days=10))
    in_bin(api, s, s.item_b, 50, s.bin2, batch=b_old, expiry=TODAY - datetime.timedelta(days=1))
    order = so(api, s, [(s.item_b, 12)])
    r = _alloc(api, order["id"], s.stage)
    flow.check(r.is_success, f"allocate B 12 ({r.status_code} {r.text[:150]})")
    _, lines = _pick_lines(api, order["id"])
    got = [(l["from_location"]["code"], l["batch_no"], float(l["qty_planned"])) for l in lines]
    want = {(s.code("BB"), b_early, 5.0), (s.code("BR"), b_early, 5.0), (s.code("BA"), b_late, 2.0)}
    flow.equal(set(got), want, "allocation: early expiry first (pickable bin then reserve), late batch last, expired never")
    flow.check(not any(b == b_old for _, b, _ in got), "expired batch was allocated")
    order_by_bin = [c for c, _, _ in got]
    flow.equal(order_by_bin, sorted(order_by_bin), "pick lines sorted by bin code")

    flow.step("F-10/F-16  Partial allocation: shortage dialog and shortage report")
    in_bin(api, s, s.item_a, 8, s.bin1)
    short = so(api, s, [(s.item_a, 20)])
    flow.goto(f"/sales-orders/{short['id']}")
    page.get_by_role("button", name="Allocate stock").click()
    dialog = page.get_by_role("dialog")
    flow.choose_in(dialog, s.code("ST"))
    dialog.get_by_role("button", name="Allocate").click()
    # Look for the dialog: the same text is also in a hidden copy antd keeps for screen readers
    flow.visible(page.get_by_role("dialog").filter(has_text="Some items are short"),
                 "shortage warning after partial allocation")
    flow.visible(page.get_by_text("short 12"), "shortage of 12 listed")
    page.keyboard.press("Escape")
    rows = [x for x in api.get("/sales-orders/shortages") if x.get("doc_no") == short["doc_no"]
            or x.get("so_id") == short["id"] or str(x).find(short["doc_no"]) >= 0]
    flow.check(len(rows) > 0, "order listed in the shortage report")
    flow.goto("/shortages")
    page.get_by_label("Search shortages").fill(short["doc_no"])  # the list is paged; the order may not be on page 1
    flow.visible(page.get_by_text(short["doc_no"]), "order shown on the shortages page")

    flow.step("F-11/F-12  Nothing available / nothing left to allocate")
    none = so(api, s, [(s.item_c if False else s.item_a, 100)])
    flow.rejected("POST", f"/sales-orders/{none['id']}/allocate", {"staging_location_id": s.stage},
                  "nothing could be allocated", "allocate with no stock left")
    full = so(api, s, [(s.item_b, 1)])
    _alloc(api, full["id"], s.stage)
    flow.rejected("POST", f"/sales-orders/{full['id']}/allocate", {"staging_location_id": s.stage},
                  "nothing left to allocate", "allocate a fully allocated SO")

    flow.step("F-13  Staging must be a DOCK")
    flow.rejected("POST", f"/sales-orders/{none['id']}/allocate", {"staging_location_id": s.bin1}, "only",
                  "staging = a BIN")


def test_f_concurrent_allocation(flow, unique):
    api = flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 10, s.bin1)
    orders = [so(api, s, [(s.item_a, 10)]) for _ in range(2)]
    flow.page.goto("/login")

    flow.step("F-15  Two orders allocate the last 10 EA at the same time")
    results = []

    def go(o):
        results.append(_alloc(api, o["id"], s.stage).status_code)

    threads = [threading.Thread(target=go, args=(o,)) for o in orders]
    [t.start() for t in threads]
    [t.join() for t in threads]
    st = stock(api, s.item_a).get((s.code("BA"), None))
    flow.equal(st, (10.0, 10.0), f"allocated never exceeds on hand (results {results})")
    flow.equal(sorted(results)[0] < 300 and sorted(results)[1] >= 400, True, f"one allocation wins ({results})")


def test_g_h_pick_and_ship(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 30, s.bin1)
    flow.sign_in()

    flow.step("G-05  Pick zero on a line, then post: whole line goes back to unallocated")
    o = so(api, s, [(s.item_a, 10)])
    _alloc(api, o["id"], s.stage)
    pick, lines = _pick_lines(api, o["id"])
    flow.goto(f"/picks/{pick['id']}")
    flow.visible(page.locator("tr.ant-table-row"), "pick lines shown")  # the route and the pick list load first
    flow.equal(page.locator("tr.ant-table-row").count(), 1, "one pick line")
    inp = page.locator("tr.ant-table-row").first.locator(".ant-input-number input")
    inp.fill("0")
    page.locator("tr.ant-table-row").first.get_by_role("button", name="Confirm").click()
    flow.visible(page.get_by_text("Short 10"), "line marked Short 10")

    flow.step("G-04  Over-pick: the field caps at the allocated qty, the API refuses")
    flow.rejected("POST", f"/picks/{pick['id']}/lines/{lines[0]['id']}/confirm", {"qty": 11}, "at most", "over-pick")

    flow.step("G-08  Post the zero pick")
    flow.confirm_action("Post pick list")
    flow.wait_status("picks", pick["id"], "POSTED")
    so_row = api.get(f"/sales-orders/{o['id']}")
    flow.equal(float(so_row["lines"][0]["unallocated"]), 10.0, "unallocated after zero pick")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (30.0, 0.0), "reservation released after zero pick")

    flow.step("H-02  Ship with nothing picked")
    flow.rejected("POST", "/shipments", {"so_id": o["id"]}, "no picked goods", "shipment with nothing picked")

    flow.step("G-07  Post with an unconfirmed line")
    _alloc(api, o["id"], s.stage)
    pick2, lines2 = _pick_lines(api, o["id"])
    flow.rejected("POST", f"/picks/{pick2['id']}/post", None, "not confirmed", "post with unconfirmed lines")

    flow.step("G-10  Cancel an open pick list in the web console: reservation released")
    flow.goto(f"/picks/{pick2['id']}")
    flow.confirm_action("Cancel pick list")
    flow.equal(flow.wait_status("picks", pick2["id"], "CANCELLED"), "CANCELLED", "pick status after cancel")
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (30.0, 0.0), "reservation released after cancel")
    flow.rejected("POST", f"/picks/{pick2['id']}/lines/{lines2[0]['id']}/confirm", {"qty": 1}, "CANCELLED",
                  "confirm on a cancelled pick")

    flow.step("G-09  Source bin locked between allocation and posting")
    _alloc(api, o["id"], s.stage)
    pick3, lines3 = _pick_lines(api, o["id"])
    api.post(f"/picks/{pick3['id']}/confirm-all")
    loc = api.get(f"/locations/{s.bin1}")
    api.call("PUT", f"/locations/{s.bin1}", {"is_locked": True, "row_version": loc["row_version"]})
    flow.rejected("POST", f"/picks/{pick3['id']}/post", None, "locked", "post pick from a locked bin")
    loc = api.get(f"/locations/{s.bin1}")
    api.call("PUT", f"/locations/{s.bin1}", {"is_locked": False, "row_version": loc["row_version"]})
    api.post(f"/picks/{pick3['id']}/post")

    flow.step("H-01/H-03  Create a shipment; a second draft is refused")
    ship = api.post("/shipments", {"so_id": o["id"], "vehicle_no": "H-01"})
    flow.equal([float(l["qty_planned"]) for l in ship["lines"]], [10.0], "shipment lines = picked goods")
    flow.rejected("POST", "/shipments", {"so_id": o["id"]}, "already has an unposted shipment", "second draft shipment")

    flow.step("H-06  Cancel the draft shipment in the web console; goods stay in staging")
    flow.goto(f"/shipments/{ship['id']}")
    flow.confirm_action("Cancel")
    flow.equal(flow.wait_status("shipments", ship["id"], "CANCELLED"), "CANCELLED", "shipment status after cancel")
    flow.equal(stock(api, s.item_a).get((s.code("ST"), None)), (10.0, 10.0), "goods still in staging, reserved for the order")

    flow.step("H-08  Staging stock moved away before posting the shipment")
    ship2 = api.post("/shipments", {"so_id": o["id"]})
    mv = api.post("/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 10,
                                        "from_location_id": s.stage, "to_location_id": s.dock_in}]})
    mv_post = api.client.post(f"/api/v1/moves/{mv['id']}/post", headers=api.headers)
    flow.check(not mv_post.is_success,
               f"picked goods waiting in staging for an open shipment could be moved away ({mv_post.status_code})")
    if mv_post.is_success:
        flow.rejected("POST", f"/shipments/{ship2['id']}/post", None, "Insufficient stock", "post after staging emptied")
        back = api.post("/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 10,
                                              "from_location_id": s.dock_in, "to_location_id": s.stage}]})
        api.post(f"/moves/{back['id']}/post")

    flow.step("H-04/H-05  Enter loading details on the draft shipment and post")
    flow.goto(f"/shipments/{ship2['id']}")
    card = page.locator(".ant-card", has_text="Loading details")
    card.get_by_label("Vehicle plate").fill("LOAD-55")
    card.get_by_label("Seal no.").fill("SEAL-55")
    card.get_by_role("button", name="Save loading details").click()
    page.wait_for_timeout(1500)
    flow.confirm_action("Post shipment")
    flow.equal(flow.wait_status("shipments", ship2["id"], "POSTED"), "POSTED", "shipment status")
    info = api.get(f"/shipments/{ship2['id']}").get("shipment_info") or {}
    flow.equal((info.get("vehicle_no"), info.get("seal_no")), ("LOAD-55", "SEAL-55"), "loading details saved")
    flow.equal(api.get(f"/sales-orders/{o['id']}")["status"], "SHIPPED", "SO status")
    flow.rejected("POST", f"/shipments/{ship2['id']}/cancel", None, "POSTED", "cancel posted shipment")

    flow.step("H-09  Print / delivery note from the shipment page")
    print_btn = page.get_by_role("button", name="Print").or_(page.get_by_role("link", name="Print"))
    flow.check(print_btn.count() > 0, "print / delivery note action on the shipment page")


def test_i_close_and_cancel(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_a, 30, s.bin1)
    flow.sign_in()

    flow.step("I-01  Cancel a confirmed SO with no activity (web)")
    o = so(api, s, [(s.item_a, 2)])
    flow.goto(f"/sales-orders/{o['id']}")
    flow.confirm_action("Cancel")
    flow.equal(flow.wait_status("sales-orders", o["id"], "CANCELLED"), "CANCELLED", "SO status")

    flow.step("I-02/I-04  Cancel / close with an open pick list")
    o = so(api, s, [(s.item_a, 4)])
    _alloc(api, o["id"], s.stage)
    flow.rejected("POST", f"/sales-orders/{o['id']}/cancel", None, "open pick lists", "cancel with open pick")
    flow.rejected("POST", f"/sales-orders/{o['id']}/close", None, "", "close with open pick")

    flow.step("I-06  Close with picked goods still in staging")
    pick, _ = _pick_lines(api, o["id"])
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    flow.rejected("POST", f"/sales-orders/{o['id']}/close", None, "ship them, or return them to stock", "close with goods in staging")
    flow.step("I-03  Cancel after a posted pick")
    flow.rejected("POST", f"/sales-orders/{o['id']}/cancel", None, "Return the picked goods to stock", "cancel after a pick")

    flow.step("I-05  Close with an unposted shipment")
    ship = api.post("/shipments", {"so_id": o["id"]})
    flow.rejected("POST", f"/sales-orders/{o['id']}/close", None, "unposted shipments", "close with draft shipment")

    flow.step("I-07  Partially shipped order closed in the web console; leaves the shortage report")
    p = so(api, s, [(s.item_a, 4), (s.item_b, 3)])
    _alloc(api, p["id"], s.stage)
    pk, _ = _pick_lines(api, p["id"])
    api.post(f"/picks/{pk['id']}/confirm-all")
    api.post(f"/picks/{pk['id']}/post")
    sh = api.post("/shipments", {"so_id": p["id"]})
    api.post(f"/shipments/{sh['id']}/post")
    flow.equal(api.get(f"/sales-orders/{p['id']}")["status"], "PARTIALLY_SHIPPED", "SO status after partial ship")
    flow.goto(f"/sales-orders/{p['id']}")
    flow.confirm_action("Close")
    flow.equal(flow.wait_status("sales-orders", p["id"], "CLOSED"), "CLOSED", "SO status after close")
    flow.check(p["doc_no"] not in str(api.get("/sales-orders/shortages")), "closed SO no longer in shortage report")
    api.post(f"/shipments/{ship['id']}/post")
