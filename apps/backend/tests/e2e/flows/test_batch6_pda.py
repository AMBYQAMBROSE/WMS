"""Batch 6 - checklist K: the PDA app (browser build) end to end: receive, put away, pick, move, count, offline."""

from playwright.sync_api import expect

from tests.conftest import ADMIN_PASSWORD
from tests.e2e.flows.kit import make_scenario, po, received, so, stock


def _sign_in(flow, pda_url):
    page = flow.page
    page.goto(f"{pda_url}/login")
    page.get_by_test_id("server-url").fill(f"{pda_url}/api/v1")
    page.get_by_test_id("username").fill("admin")
    page.get_by_test_id("password").fill(ADMIN_PASSWORD)
    page.get_by_test_id("login").click()
    expect(page.get_by_test_id("menu-receive")).to_be_enabled(timeout=30_000)


def _scan(page, test_id, code):
    field = page.get_by_test_id(test_id)
    expect(field).to_be_editable(timeout=15_000)
    field.fill(code)
    field.press("Enter")


def _home(page, pda_url):
    page.goto(f"{pda_url}/")
    expect(page.get_by_test_id("menu-receive")).to_be_visible(timeout=20_000)


def _banner(page, timeout=20_000) -> str:
    b = page.get_by_test_id("banner").last
    try:
        b.wait_for(state="visible", timeout=timeout)
        return b.inner_text()
    except Exception:  # noqa: BLE001
        return ""


def test_k_pda_full_flow(flow, unique, pda_url):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    order = po(api, s, [(s.item_a, 20)])
    _sign_in(flow, pda_url)

    flow.step("K-03  PDA receive: scan PO, dock, item, qty 20, submit")
    page.get_by_test_id("menu-receive").click()
    _scan(page, "scan-po", order["doc_no"])
    _scan(page, "scan-location", s.code("IN"))
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("20")
    page.get_by_test_id("confirm-entry").click()
    page.get_by_test_id("submit-receive").click()
    flow.visible(page.get_by_text("Received, document no."), "receipt confirmation on the PDA", timeout=30_000)
    flow.equal(stock(api, s.item_a).get((s.code("IN"), None)), (20.0, 0.0), "dock stock after PDA receipt")

    flow.step("K-04  Unknown barcode on the putaway item scan")
    _home(page, pda_url)
    page.get_by_test_id("menu-putaway").click()
    page.get_by_test_id("putaway-free").click()  # the free putaway, without a sheet
    _scan(page, "scan-from", s.code("IN"))
    _scan(page, "scan-item", f"NOPE{unique}")
    text = _banner(page)
    flow.check(bool(text), "a message is shown for an unknown barcode")

    flow.step("K-03  PDA putaway: dock -> BA, 20 EA")
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("20")
    _scan(page, "scan-target", s.code("BA"))
    page.get_by_test_id("submit-putaway").click()
    flow.visible(page.get_by_text("done, document no."), "putaway confirmation on the PDA", timeout=30_000)
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (20.0, 0.0), "bin stock after PDA putaway")

    flow.step("K-03  PDA move: BA -> BB, 5 EA")
    _home(page, pda_url)
    page.get_by_test_id("menu-move").click()
    _scan(page, "scan-from", s.code("BA"))
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("5")
    _scan(page, "scan-target", s.code("BB"))
    page.get_by_test_id("submit-move").click()
    flow.visible(page.get_by_text("done, document no."), "move confirmation on the PDA", timeout=30_000)
    st = stock(api, s.item_a)
    flow.equal((st.get((s.code("BA"), None)), st.get((s.code("BB"), None))), ((15.0, 0.0), (5.0, 0.0)), "after PDA move")

    flow.step("G-12  PDA guided pick: wrong bin and wrong item are refused, then pick 15")
    o = so(api, s, [(s.item_a, 15)])
    api.post(f"/sales-orders/{o['id']}/allocate", {"staging_location_id": s.stage})
    pick = [p for p in api.get("/picks", so_id=o["id"]) if p["status"] == "OPEN"][0]
    _home(page, pda_url)
    page.get_by_test_id("menu-pick").click()
    page.get_by_test_id(f"pick-{pick['doc_no']}").click()
    expect(page.get_by_test_id("target-bin")).to_have_text(s.code("BA"), timeout=15_000)
    _scan(page, "scan-bin", s.code("BB"))
    flow.check(page.get_by_test_id("scan-item").count() == 0, "wrong bin scan must not advance to the item step")
    _scan(page, "scan-bin", s.code("BA"))
    _scan(page, "scan-item", s.b)
    flow.check(page.get_by_test_id("qty").count() == 0, "wrong item scan must not advance to the quantity step")
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("15")
    page.get_by_test_id("confirm-pick").click()
    page.get_by_test_id("finish-pick").click()
    page.wait_for_timeout(3000)
    flow.equal(api.get(f"/picks/{pick['id']}")["status"], "POSTED", "pick list posted from the PDA")
    flow.equal(stock(api, s.item_a).get((s.code("ST"), None)), (15.0, 0.0), "staging after PDA pick")

    flow.step("K-03  PDA count: BB counted 4 (book 5)")
    cc = api.post("/cycle-counts", {"location_ids": [s.bin2]})
    _home(page, pda_url)
    page.get_by_test_id("menu-count").click()
    page.get_by_test_id(f"count-{cc['doc_no']}").click()
    _scan(page, "scan-count-location", s.code("BB"))
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("4")
    page.get_by_test_id("confirm-count").click()
    page.wait_for_timeout(2500)
    lines = api.get(f"/cycle-counts/{cc['id']}")["lines"]
    flow.equal([float(l["qty_actual"]) for l in lines if l["counted_at"]], [4.0], "count entered from the PDA")
    api.post(f"/cycle-counts/{cc['id']}/cancel")


def test_k_pda_offline_putaway(flow, unique, pda_url):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    received(api, s, s.item_a, 8)
    _sign_in(flow, pda_url)

    flow.step("K-05  Offline putaway: queued on the device, submitted once online, no duplicate")
    page.get_by_test_id("menu-putaway").click()
    page.get_by_test_id("putaway-free").click()  # the free putaway, without a sheet
    _scan(page, "scan-from", s.code("IN"))
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("8")
    _scan(page, "scan-target", s.code("BA"))
    page.context.set_offline(True)
    page.get_by_test_id("submit-putaway").click()
    flow.visible(page.get_by_text("Saved on this device"), "offline submit kept on the device", timeout=20_000)
    page.wait_for_timeout(1500)
    page.context.set_offline(False)
    for _ in range(40):
        if stock(api, s.item_a).get((s.code("BA"), None)):
            break
        page.wait_for_timeout(1000)
    flow.equal(stock(api, s.item_a).get((s.code("BA"), None)), (8.0, 0.0), "putaway submitted once back online")
    ins = [r for r in api.get("/stock/ledger", item_id=s.item_a, limit=100) if r["movement_type"] == "PUTAWAY_IN"]
    flow.equal(len(ins), 1, "exactly one putaway posted from the queued submit")

    flow.step("K-06  Business error in the queue: over-putaway queued offline is marked failed")
    received(api, s, s.item_a, 2)
    _home(page, pda_url)
    page.get_by_test_id("menu-putaway").click()
    page.get_by_test_id("putaway-free").click()  # the free putaway, without a sheet
    _scan(page, "scan-from", s.code("IN"))
    _scan(page, "scan-item", s.a)
    page.get_by_test_id("qty").fill("2")
    _scan(page, "scan-target", s.code("BA"))
    page.context.set_offline(True)
    page.get_by_test_id("submit-putaway").click()
    page.wait_for_timeout(1000)
    mv = api.post("/moves", {"lines": [{"item_id": s.item_a, "uom_id": s.ea, "qty": 2,
                                        "from_location_id": s.dock_in, "to_location_id": s.bin2}]})
    api.post(f"/moves/{mv['id']}/post")  # someone else takes the goods meanwhile
    page.context.set_offline(False)
    page.wait_for_timeout(8000)
    _home(page, pda_url)
    page.get_by_test_id("menu-queue").click()
    flow.visible(page.get_by_test_id("failed-ops"), "failed operation listed in the queue", timeout=30_000)
    flow.visible(page.get_by_text("Insufficient stock"), "server reason shown for the failed operation")
