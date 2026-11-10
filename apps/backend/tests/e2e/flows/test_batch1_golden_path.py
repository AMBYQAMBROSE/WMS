"""Batch 1 - checklist part A: the golden path through the web console, receiving -> putaway -> shipping."""

import datetime

from playwright.sync_api import expect

from tests.e2e.flows.kit import TODAY, ledger_totals, make_scenario, stock


def _rows(page):
    return page.locator(".ant-table-tbody tr.ant-table-row")


def test_golden_path(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    L1, L2 = f"L1-{unique}", f"L2-{unique}"
    exp1, exp2 = TODAY + datetime.timedelta(days=90), TODAY + datetime.timedelta(days=30)
    flow.sign_in()

    # ---------------------------------------------------------------- A-01 purchase order
    flow.step("A-01  New purchase order: A 5 CTN + A 40 EA (=100 EA), B 50 EA")
    flow.goto("/purchase-orders/new")
    flow.choose("Supplier", s.supplier_code)
    rows = page.locator(".wms-lines-row")
    flow.choose_in(rows.nth(0), s.a)
    flow.choose(rows.nth(0).locator(".ant-select").nth(1), "CTN")
    page.get_by_label("Quantity, line 1").fill("5")
    page.get_by_role("button", name="Add line").click()
    flow.choose_in(rows.nth(1), s.a)
    page.get_by_label("Quantity, line 2").fill("40")
    page.get_by_role("button", name="Add line").click()
    flow.choose_in(rows.nth(2), s.b)
    page.get_by_label("Quantity, line 3").fill("50")
    page.get_by_role("button", name="Save", exact=True).click()
    po_id = flow.wait_doc("purchase-orders")
    po = api.get(f"/purchase-orders/{po_id}")
    flow.equal(po["status"], "DRAFT", "new PO status")
    flow.equal([(l["item"]["sku_code"], l["uom"]["code"], float(l["qty_planned"])) for l in po["lines"]],
               [(s.a, "CTN", 5.0), (s.a, "EA", 40.0), (s.b, "EA", 50.0)], "PO lines")

    # ---------------------------------------------------------------- A-02 confirm
    flow.step("A-02  Confirm the purchase order")
    flow.confirm_action("Confirm")
    flow.equal(flow.wait_status("purchase-orders", po_id, "CONFIRMED"), "CONFIRMED", "PO status after confirm")

    # ---------------------------------------------------------------- A-03 GRN-1
    flow.step(f"A-03  GRN-1 to the receiving dock: A 5 CTN, B 30 batch {L1}")
    page.get_by_role("button", name="Receive").click()
    page.wait_for_url("**/grns/new?po=*")
    flow.loaded()
    flow.choose("Receiving location", s.code("IN"))
    page.get_by_label("Received quantity, line 1").fill("5")
    page.get_by_label("Received quantity, line 2").fill("0")
    page.get_by_label("Received quantity, line 3").fill("30")
    b_row = _rows(page).nth(2)
    b_row.locator("input[placeholder='Required']").fill(L1)
    flow.pick_date(b_row, exp1)
    page.get_by_role("button", name="Create goods receipt").click()
    po_lines = api.get(f"/purchase-orders/{po_id}")["lines"]
    grn1 = flow.saved("grns", lambda: api.post("/grns", {"po_id": po_id, "location_id": s.dock_in, "lines": [
        {"po_line_id": po_lines[0]["id"], "qty": 5},
        {"po_line_id": po_lines[2]["id"], "qty": 30, "batch_no": L1, "expiry_date": exp1.isoformat()},
    ]}), "Create GRN-1")
    flow.step("A-03  Post GRN-1")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("grns", grn1, "POSTED"), "POSTED", "GRN-1 status")
    flow.equal(api.get(f"/purchase-orders/{po_id}")["status"], "PARTIALLY_RECEIVED", "PO status after GRN-1")
    flow.equal(stock(api, s.item_a), {(s.code("IN"), None): (60.0, 0.0)}, "A stock after GRN-1 (5 CTN = 60 EA)")
    flow.equal(stock(api, s.item_b), {(s.code("IN"), L1): (30.0, 0.0)}, "B stock after GRN-1")

    # ---------------------------------------------------------------- A-04 GRN-2
    flow.step(f"A-04  GRN-2: the rest - A 40 EA, B 20 batch {L2}")
    flow.goto(f"/purchase-orders/{po_id}")
    page.get_by_role("button", name="Receive").click()
    page.wait_for_url("**/grns/new?po=*")
    flow.loaded()
    flow.equal(_rows(page).count(), 2, "GRN-2 prefilled lines (fully received line left out)")
    flow.choose("Receiving location", s.code("IN"))
    b_row = _rows(page).nth(1)
    b_row.locator("input[placeholder='Required']").fill(L2)
    flow.pick_date(b_row, exp2)
    page.get_by_role("button", name="Create goods receipt").click()
    grn2 = flow.saved("grns", lambda: api.post("/grns", {"po_id": po_id, "location_id": s.dock_in, "lines": [
        {"po_line_id": po_lines[1]["id"], "qty": 40},
        {"po_line_id": po_lines[2]["id"], "qty": 20, "batch_no": L2, "expiry_date": exp2.isoformat()},
    ]}), "Create GRN-2")
    flow.confirm_action("Post")
    flow.equal(flow.wait_status("grns", grn2, "POSTED"), "POSTED", "GRN-2 status")
    flow.equal(api.get(f"/purchase-orders/{po_id}")["status"], "RECEIVED", "PO status after GRN-2")
    flow.equal(stock(api, s.item_a), {(s.code("IN"), None): (100.0, 0.0)}, "A stock after GRN-2")
    flow.equal(stock(api, s.item_b), {(s.code("IN"), L1): (30.0, 0.0), (s.code("IN"), L2): (20.0, 0.0)},
               "B stock after GRN-2")

    # ---------------------------------------------------------------- A-05 putaway
    for grn_id, label in ((grn1, "GRN-1"), (grn2, "GRN-2")):
        flow.step(f"A-05  Putaway from {label}: A -> {s.code('BA')}, B -> {s.code('BB')}")
        flow.goto(f"/grns/{grn_id}")
        page.get_by_role("button", name="Create putaway").click()
        page.wait_for_url("**/putaways/new?grn=*")
        flow.loaded()
        lines = _rows(page)
        flow.equal(lines.count(), 2, f"putaway lines prefilled from {label}")
        for i in range(lines.count()):
            sku = lines.nth(i).inner_text()
            target = s.code("BB") if s.b in sku or "Item B" in sku else s.code("BA")
            flow.choose(lines.nth(i).locator(".ant-select").last, target)
        page.get_by_role("button", name="Create putaway").click()
        pa = flow.wait_doc("putaways")
        flow.confirm_action("Post")
        flow.equal(flow.wait_status("putaways", pa, "POSTED"), "POSTED", f"putaway from {label} status")
    flow.equal(stock(api, s.item_a), {(s.code("BA"), None): (100.0, 0.0)}, "A stock after putaway")
    flow.equal(stock(api, s.item_b), {(s.code("BB"), L1): (30.0, 0.0), (s.code("BB"), L2): (20.0, 0.0)},
               "B stock after putaway")

    # ---------------------------------------------------------------- A-06 sales order
    flow.step("A-06  New sales order: A 70, B 25 -> confirm")
    flow.goto("/sales-orders/new")
    flow.choose("Customer", s.customer_code)
    rows = page.locator(".wms-lines-row")
    flow.choose_in(rows.nth(0), s.a)
    page.get_by_label("Quantity, line 1").fill("70")
    page.get_by_role("button", name="Add line").click()
    flow.choose_in(rows.nth(1), s.b)
    page.get_by_label("Quantity, line 2").fill("25")
    page.get_by_role("button", name="Save", exact=True).click()
    so_id = flow.wait_doc("sales-orders")
    flow.confirm_action("Confirm")
    flow.equal(flow.wait_status("sales-orders", so_id, "CONFIRMED"), "CONFIRMED", "SO status after confirm")

    # ---------------------------------------------------------------- A-07 allocate
    def allocate():
        page.get_by_role("button", name="Allocate stock").click()
        dialog = page.get_by_role("dialog")
        flow.choose_in(dialog, s.code("ST"))
        dialog.get_by_role("button", name="Allocate").click()
        expect(dialog).to_be_hidden(timeout=15_000)

    flow.step("A-07  Allocate to staging: expect B batch with the earlier expiry (L2) first")
    allocate()
    flow.equal(stock(api, s.item_a), {(s.code("BA"), None): (100.0, 70.0)}, "A allocated")
    flow.equal(stock(api, s.item_b), {(s.code("BB"), L1): (30.0, 5.0), (s.code("BB"), L2): (20.0, 20.0)},
               "B allocated FEFO (L2 20, then L1 5)")
    picks = api.get("/picks", so_id=so_id)
    flow.equal(len(picks), 1, "pick lists after first allocation")
    pick1 = picks[0]["id"]

    # ---------------------------------------------------------------- A-08 pick with a short pick
    flow.step(f"A-08  Pick list: short-pick B {L1} (2 of 5), confirm the rest, post")
    flow.goto(f"/picks/{pick1}")
    l1_row = page.locator("tr.ant-table-row", has_text=L1)
    l1_row.locator(".ant-input-number input").fill("2")
    l1_row.get_by_role("button", name="Confirm").click()
    expect(l1_row.get_by_text("Short 3")).to_be_visible(timeout=10_000)
    page.get_by_role("button", name="Confirm all unconfirmed lines at the allocated quantity (2)").click()
    expect(page.get_by_text("0 of 3 to confirm")).to_be_visible(timeout=10_000)
    flow.confirm_action("Post pick list")
    flow.equal(flow.wait_status("picks", pick1, "POSTED"), "POSTED", "pick list 1 status")
    flow.equal(api.get(f"/sales-orders/{so_id}")["status"], "IN_PROGRESS", "SO status after picking")
    flow.equal(stock(api, s.item_a), {(s.code("BA"), None): (30.0, 0.0), (s.code("ST"), None): (70.0, 0.0)},
               "A after pick")
    flow.equal(stock(api, s.item_b), {(s.code("BB"), L1): (28.0, 0.0), (s.code("ST"), L1): (2.0, 0.0),
                                      (s.code("ST"), L2): (20.0, 0.0)}, "B after pick (short pick released)")
    so = api.get(f"/sales-orders/{so_id}")
    flow.equal([float(l["unallocated"]) for l in so["lines"]], [0.0, 3.0], "SO unallocated after short pick")

    # ---------------------------------------------------------------- A-09 ship
    def ship(plate: str):
        flow.goto(f"/sales-orders/{so_id}")
        page.get_by_role("button", name="Ship", exact=True).click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Carrier").fill("Test Carrier")
        dialog.get_by_label("Vehicle plate").fill(plate)
        dialog.get_by_label("Seal no.").fill(f"SEAL-{plate}")
        dialog.get_by_label("Driver", exact=True).fill("Driver One")
        dialog.get_by_role("button", name="Create shipment").click()
        ship_id = flow.wait_doc("shipments")
        plates = page.locator("input").evaluate_all("els => els.map(e => e.value)")
        flow.check(plate in plates or page.get_by_text(plate).count() > 0, "vehicle plate shown on the shipment")
        flow.confirm_action("Post shipment")
        flow.equal(flow.wait_status("shipments", ship_id, "POSTED"), "POSTED", "shipment status")
        return ship_id

    flow.step("A-09  Ship everything in staging (vehicle, seal, driver) and post")
    ship("TRK-001")
    flow.equal(api.get(f"/sales-orders/{so_id}")["status"], "PARTIALLY_SHIPPED", "SO status after first shipment")
    flow.equal(stock(api, s.item_a), {(s.code("BA"), None): (30.0, 0.0)}, "A after first shipment")
    flow.equal(stock(api, s.item_b), {(s.code("BB"), L1): (28.0, 0.0)}, "B after first shipment")

    # ---------------------------------------------------------------- A-10 second round
    flow.step("A-10  Allocate the 3 short-picked B again, pick, ship")
    flow.goto(f"/sales-orders/{so_id}")
    allocate()
    picks = [p for p in api.get("/picks", so_id=so_id) if p["status"] == "OPEN"]
    flow.equal(len(picks), 1, "open pick lists after re-allocation")
    if picks:
        flow.goto(f"/picks/{picks[0]['id']}")
        page.get_by_role("button", name="Confirm all unconfirmed lines at the allocated quantity (1)").click()
        expect(page.get_by_text("0 of 1 to confirm")).to_be_visible(timeout=10_000)
        flow.confirm_action("Post pick list")
        flow.wait_status("picks", picks[0]["id"], "POSTED")
    ship("TRK-002")
    flow.equal(api.get(f"/sales-orders/{so_id}")["status"], "SHIPPED", "SO status after last shipment")

    # ---------------------------------------------------------------- A-11 reconcile
    flow.step("A-11  Reconcile: ledger totals = stock on hand; nothing allocated")
    a, b = stock(api, s.item_a), stock(api, s.item_b)
    flow.equal(a, {(s.code("BA"), None): (30.0, 0.0)}, "final A stock")
    flow.equal(b, {(s.code("BB"), L1): (25.0, 0.0)}, "final B stock")
    flow.equal(ledger_totals(api, s.item_a), {k: v[0] for k, v in a.items()}, "A ledger vs balance")
    flow.equal(ledger_totals(api, s.item_b), {k: v[0] for k, v in b.items()}, "B ledger vs balance")
    flow.goto("/stock")
    page.wait_for_timeout(800)

    # ---------------------------------------------------------------- A-12 / A-13 reports and audit
    flow.step("A-12  Dashboard and turnover report")
    flow.goto("/dashboard")
    page.wait_for_timeout(1500)
    flow.goto("/reports/turnover")
    page.wait_for_timeout(1500)
    turnover = api.get("/reports/turnover", date_from=TODAY.isoformat(), date_to=TODAY.isoformat(), limit=500)
    rows = turnover.get("rows", turnover) if isinstance(turnover, dict) else turnover
    mine = [r for r in rows if str(r.get("sku_code", "")).endswith(unique)]
    flow.check(len(mine) >= 2, f"turnover report has rows for A and B today (got {len(mine)})")

    flow.step("A-13  Audit trail of the purchase order and sales order")
    flow.check(len(api.get("/audit-logs", entity_id=po_id)) > 0, "audit entries for the PO")
    flow.check(len(api.get("/audit-logs", entity_id=so_id)) > 0, "audit entries for the SO")
    flow.goto("/audit-log")
    page.wait_for_timeout(1000)
