"""PDA app (browser build): scanning flows and the offline submit queue against the real API."""

from playwright.sync_api import Page, expect

from tests.conftest import ADMIN_PASSWORD
from tests.helpers import Api, make_item, make_warehouse


def pda_sign_in(page: Page, pda_url: str, username: str = "admin", password: str = ADMIN_PASSWORD) -> None:
    page.goto(f"{pda_url}/login")
    page.get_by_test_id("server-url").fill(f"{pda_url}/api/v1")
    page.get_by_test_id("username").fill(username)
    page.get_by_test_id("password").fill(password)
    page.get_by_test_id("login").click()
    expect(page.get_by_test_id("menu-receive")).to_be_enabled(timeout=15_000)  # master data downloaded


def scan(page: Page, test_id: str, code: str) -> None:
    """A scanner types the code and presses Enter"""
    field = page.get_by_test_id(test_id)
    expect(field).to_be_editable()
    field.fill(code)
    field.press("Enter")


def test_receive_on_the_pda(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"PD{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 5}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")

    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-receive").click()
    scan(page, "scan-po", po["doc_no"])
    scan(page, "scan-location", f"IN{unique}")
    scan(page, "scan-item", f"PD{unique}")
    page.get_by_test_id("qty").fill("3")
    page.get_by_test_id("confirm-entry").click()
    page.get_by_test_id("submit-receive").click()

    expect(page.get_by_text("Received, document no.")).to_be_visible(timeout=15_000)
    grns = api.get("/grns", keyword=po["doc_no"])
    assert [(g["status"]) for g in grns] == ["POSTED"]


def _prepare_receipt(page: Page, po: dict, unique: str, qty: str) -> None:
    """Online: open the order and enter a line, so only the submit happens offline"""
    page.get_by_test_id("menu-receive").click()
    scan(page, "scan-po", po["doc_no"])
    scan(page, "scan-location", f"IN{unique}")
    scan(page, "scan-item", f"PD{unique}")
    page.get_by_test_id("qty").fill(qty)
    page.get_by_test_id("confirm-entry").click()


def _confirmed_po(api: Api, unique: str, qty: int = 5) -> tuple[dict, object]:
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"PD{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": qty}]})
    api.post(f"/purchase-orders/{po['id']}/confirm")
    return po, wh


def _sign_out(page: Page, pda_url: str | None = None) -> None:
    """From the home screen; without pda_url by going back in the app, which also works offline"""
    if pda_url:
        page.goto(f"{pda_url}/")
    else:
        page.go_back()
    page.get_by_text("Sign out").click()
    expect(page.get_by_test_id("login")).to_be_visible()


def test_queued_work_is_submitted_only_by_its_own_user(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    po, _ = _confirmed_po(api, unique)
    api.post("/users", {"username": f"pdb{unique}", "display_name": "B", "password": "Pda@Test123", "role_codes": ["ADMIN"]})

    pda_sign_in(page, pda_url)  # worker A (admin)
    _prepare_receipt(page, po, unique, "2")
    page.context.set_offline(True)
    page.get_by_test_id("submit-receive").click()
    expect(page.get_by_text("Saved on this device")).to_be_visible(timeout=20_000)

    # Shift change while the network is still down: A signs out, B signs in once it is back.
    # A's receipt must not be posted under B's name.
    _sign_out(page)
    page.context.set_offline(False)
    pda_sign_in(page, pda_url, f"pdb{unique}", "Pda@Test123")
    page.goto(f"{pda_url}/queue")
    held = page.get_by_test_id("held-for-others")
    expect(held).to_contain_text(f"PD{unique} × 2")
    page.wait_for_timeout(2_000)
    assert api.get("/grns", keyword=po["doc_no"]) == []

    # A signs in again: submitted, recorded as A's work
    _sign_out(page, pda_url)
    pda_sign_in(page, pda_url)
    expect(page.get_by_test_id("sync-indicator")).not_to_contain_text("Pending", timeout=15_000)
    grns = api.get("/grns", keyword=po["doc_no"])
    assert [g["status"] for g in grns] == ["POSTED"]
    created = [e for e in api.get("/audit-logs", entity_id=grns[0]["id"]) if e["action"] == "CREATE" and e["entity_type"] == "document"]
    assert created[0]["username"] == "admin"


def test_failed_operation_shows_details_and_can_be_retried(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    po, wh = _confirmed_po(api, unique)

    pda_sign_in(page, pda_url)
    _prepare_receipt(page, po, unique, "2")
    page.context.set_offline(True)
    page.get_by_test_id("submit-receive").click()
    expect(page.get_by_text("Saved on this device")).to_be_visible(timeout=20_000)

    # Meanwhile the receiving location gets locked: the queued receipt will be rejected when it syncs
    api.call("PUT", f"/locations/{wh.dock_in}", {"is_locked": True})
    page.context.set_offline(False)
    page.goto(f"{pda_url}/queue")
    # The queue syncs by itself once back online (and every 20 s); the receipt is rejected
    failed = page.get_by_test_id("failed-ops")
    expect(failed).to_contain_text("locked", timeout=30_000)
    expect(failed).to_contain_text(f"Into IN{unique}")
    expect(failed).to_contain_text(f"PD{unique} × 2")

    # Fixed: unlocked; the retry goes through
    api.call("PUT", f"/locations/{wh.dock_in}", {"is_locked": False})
    page.get_by_test_id("retry-op").click()
    expect(failed).to_have_count(0, timeout=15_000)
    expect(page.get_by_text(f"Receive {po['doc_no']} → GRN")).to_be_visible(timeout=15_000)  # under recently completed
    assert [g["status"] for g in api.get("/grns", keyword=po["doc_no"])] == ["POSTED"]


def test_new_pick_list_is_announced(page: Page, pda_url, client, admin_headers, unique):
    from tests.helpers import put_away, receive

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"NW{unique}")
    receive(api, wh, item, 4)
    put_away(api, wh, item, 4)

    pda_sign_in(page, pda_url)
    page.wait_for_timeout(2_000)  # the first check records the work that already exists
    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 2}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})

    pick_button = page.get_by_test_id("menu-pick")
    expect(pick_button).to_contain_text("1 new", timeout=30_000)  # next check within 20 s
    expect(page.get_by_text("New work: 1 pick list")).to_be_visible()

    pick_button.click()
    # The screen itself, not just the URL: the browser build loads screens lazily, and leaving before it mounted
    # would leave the alert set (it is cleared when the operator actually sees the pick screen)
    expect(page.get_by_text("Refresh")).to_be_visible()
    page.go_back()
    expect(pick_button).not_to_contain_text("new")


def test_each_scan_counts_one_when_receiving(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    po, _ = _confirmed_po(api, unique, qty=10)

    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-receive").click()
    scan(page, "scan-po", po["doc_no"])
    scan(page, "scan-location", f"IN{unique}")
    page.get_by_test_id("each-scan").click()
    for _ in range(3):
        scan(page, "scan-item", f"PD{unique}")
    expect(page.get_by_text(f"PD{unique} +1, now 3")).to_be_visible()
    expect(page.get_by_test_id("qty")).to_have_count(0)  # no quantity panel
    page.get_by_test_id("submit-receive").click()

    expect(page.get_by_text("Received, document no.")).to_be_visible(timeout=15_000)
    grn = api.get(f"/grns/{api.get('/grns', keyword=po['doc_no'])[0]['id']}")
    assert [float(line["qty_actual"]) for line in grn["lines"]] == [3]


def test_each_scan_counts_one_when_counting(page: Page, pda_url, client, admin_headers, unique):
    from tests.helpers import put_away, receive

    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"CT{unique}")
    receive(api, wh, item, 6)
    put_away(api, wh, item, 6)
    count = api.post("/cycle-counts", {"location_ids": [wh.bin], "remark": f"each-{unique}"})

    pda_sign_in(page, pda_url)
    page.get_by_test_id("menu-count").click()
    page.get_by_text(f"{count['doc_no']} · each-{unique}").click()
    scan(page, "scan-count-location", f"BIN{unique}")
    page.get_by_test_id("each-scan").click()
    for _ in range(4):
        scan(page, "scan-item", f"CT{unique}")
    expect(page.get_by_test_id("qty")).to_have_value("4")
    page.get_by_test_id("confirm-count").click()

    expect(page.get_by_text(f"Recorded CT{unique} = 4")).to_be_visible(timeout=15_000)
    line = api.get(f"/cycle-counts/{count['id']}")["lines"][0]
    assert float(line["qty_actual"]) == 4


def test_photo_taken_offline_reaches_the_receipt(page: Page, pda_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    po, _ = _confirmed_po(api, unique)
    jpeg = page.screenshot(type="jpeg")  # a real JPEG for the browser build's "camera" (a file chooser)

    pda_sign_in(page, pda_url)
    _prepare_receipt(page, po, unique, "2")
    page.context.set_offline(True)
    page.get_by_test_id("photo-note").fill("Torn box")
    with page.expect_file_chooser() as chooser:
        page.get_by_test_id("take-photo").click()
    chooser.value.set_files({"name": "damage.jpg", "mimeType": "image/jpeg", "buffer": jpeg})
    expect(page.get_by_test_id("photo-thumb")).to_have_count(1)
    page.get_by_test_id("submit-receive").click()
    expect(page.get_by_text("Saved on this device")).to_be_visible(timeout=20_000)

    page.context.set_offline(False)
    page.goto(f"{pda_url}/queue")
    expect(page.get_by_text(f"Receive {po['doc_no']} → GRN")).to_be_visible(timeout=30_000)

    grn = api.get("/grns", keyword=po["doc_no"])[0]
    photos = api.get(f"/documents/{grn['id']}/attachments")
    assert [(p["caption"], p["content_type"], p["created_by"]) for p in photos] == [("Torn box", "image/jpeg", "admin")]
    image = client.get(f"/api/v1/attachments/{photos[0]['id']}/content", headers=admin_headers).content
    assert image[:3] == b"\xff\xd8\xff"
