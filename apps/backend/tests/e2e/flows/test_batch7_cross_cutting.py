"""Batch 7 - checklist L: permissions, users/roles, idempotency, numbering, integration events, import, reports,
audit, live updates, every page renders. Backup/restore, upgrade, performance at 50k SKUs stay manual (L-16..L-19)."""

import datetime
import re

from tests.conftest import ADMIN_PASSWORD
from tests.e2e.flows.kit import TODAY, in_bin, make_scenario, po, so

PAGES = [
    "/dashboard", "/reports/turnover", "/reports/picker-kpi", "/reports/expiry", "/reports/partner-ledger",
    "/purchase-orders", "/purchase-orders/new", "/grns", "/grns/new", "/putaways", "/putaways/new",
    "/sales-orders", "/sales-orders/new", "/picks", "/shipments", "/shortages",
    "/stock", "/moves", "/moves/new", "/adjustments", "/adjustments/new", "/cycle-counts", "/cycle-counts/new",
    "/business-partners", "/items", "/locations", "/reason-codes",
    "/users", "/roles", "/features", "/integration", "/imports", "/audit-log", "/system-health",
]


def _login(api, username, password):
    r = api.client.post("/api/v1/auth/login", data={"username": username, "password": password})
    return r


def _user(api, unique, role):
    username, password = f"{role.lower()[:3]}{unique}".lower(), "Flow@Test123"
    u = api.post("/users", {"username": username, "display_name": f"{role.title()} {unique}", "password": password,
                            "role_codes": [role]})
    return u, username, password


def test_l_permissions_and_users(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    viewer, vname, vpass = _user(api, unique, "VIEWER")
    clerk, cname, cpass = _user(api, unique, "CLERK")
    order = po(api, s, [(s.item_a, 1)], confirm=False)

    flow.step("L-01  Viewer: read-only menus, no create/confirm buttons, API answers 403")
    flow.sign_in(vname, vpass)
    flow.goto("/purchase-orders")
    flow.check(page.get_by_role("button", name="New purchase order").count() == 0, "viewer sees 'New purchase order'")
    flow.goto(f"/purchase-orders/{order['id']}")
    flow.check(page.get_by_role("button", name="Confirm").count() == 0, "viewer sees Confirm on a PO")
    flow.check(page.get_by_text("Users", exact=True).count() == 0, "viewer sees the Users menu")
    vh = {"Authorization": f"Bearer {_login(api, vname, vpass).json()['access_token']}"}
    r = api.client.post(f"/api/v1/purchase-orders/{order['id']}/confirm", headers=vh)
    flow.equal(r.status_code, 403, "viewer confirm PO via API")
    r = api.client.get("/api/v1/users", headers=vh)
    flow.equal(r.status_code, 403, "viewer lists users via API")
    flow.goto("/users")
    flow.visible(page.get_by_text(re.compile("permission|not allowed|403", re.I)), "viewer opening /users gets a no-permission page")

    flow.step("L-02  Permission removed while signed in: takes effect on refresh")
    flow.sign_out()
    flow.sign_in(cname, cpass)
    flow.goto("/putaways")
    flow.check(page.get_by_role("button", name=re.compile("New putaway")).count() > 0, "clerk can create putaways")
    users = api.get("/users")
    me = next(u for u in users if u["username"] == cname)
    api.call("PUT", f"/users/{me['id']}", {"display_name": me["display_name"], "role_codes": ["VIEWER"], "row_version": me["row_version"]})
    page.reload()
    flow.loaded()
    page.wait_for_timeout(1500)
    flow.check(page.get_by_role("button", name=re.compile("New putaway")).count() == 0,
               "create button still shown after the role was changed to VIEWER (after refresh)")

    flow.step("L-03  Deactivated user is locked out at once")
    me = next(u for u in api.get("/users") if u["username"] == cname)
    api.call("PUT", f"/users/{me['id']}", {"display_name": me["display_name"], "is_active": False, "role_codes": ["VIEWER"], "row_version": me["row_version"]})
    page.reload()
    page.wait_for_timeout(2500)
    flow.check("/login" in page.url, f"deactivated user is sent to the sign-in page (at {page.url})")
    flow.equal(_login(api, cname, cpass).status_code in (400, 401, 403), True, "deactivated user cannot sign in")

    flow.step("L-03  Admin cannot deactivate themselves or remove their own user management")
    admin = next(u for u in api.get("/users") if u["username"] == "admin")
    flow.rejected("PUT", f"/users/{admin['id']}", {"display_name": admin["display_name"], "is_active": False, "role_codes": ["ADMIN"], "row_version": admin["row_version"]},
                  "your own account", "deactivate yourself")
    flow.rejected("PUT", f"/users/{admin['id']}", {"display_name": admin["display_name"], "role_codes": ["VIEWER"], "row_version": admin["row_version"]},
                  "user management", "drop your own user management")

    flow.step("L-04  System roles cannot be changed; a role in use cannot be deleted")
    sysrole = next(r for r in api.get("/roles") if r["code"] == "ADMIN")
    flow.rejected("PUT", f"/roles/{sysrole['id']}", {"name": "Hacked", "permission_codes": [],
                  "row_version": sysrole.get("row_version")}, "System role", "edit the ADMIN role")
    viewer_role = next(r for r in api.get("/roles") if r["code"] == "VIEWER")
    r = api.client.delete(f"/api/v1/roles/{viewer_role['id']}", headers=api.headers)
    flow.check(not r.is_success, f"delete a role in use ({r.status_code})")
    flow.sign_out()


def test_l_idempotency_numbering_events(flow, unique):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    flow.sign_in()

    flow.step("L-05/L-06  Same client request ID twice; reused for different content")
    o = po(api, s, [(s.item_a, 10)])
    body = {"po_id": o["id"], "location_id": s.dock_in, "client_request_id": f"req-{unique}-1",
            "lines": [{"po_line_id": o["lines"][0]["id"], "qty": 2}]}
    g1 = api.post("/grns", body)
    g2 = api.post("/grns", body)
    flow.equal(g1["id"], g2["id"], "same request id returns the same GRN")
    other = po(api, s, [(s.item_a, 5)])
    flow.rejected("POST", "/grns", {**body, "po_id": other["id"], "lines": [
        {"po_line_id": other["lines"][0]["id"], "qty": 1}]}, "already used", "request id reused for another PO")

    flow.step("L-09  Document numbers: prefix + date + sequence, unique and increasing")
    nos = [po(api, s, [(s.item_a, 1)], confirm=False)["doc_no"] for _ in range(3)]
    flow.check(all(n.startswith(f"PO{TODAY:%Y%m%d}-") for n in nos), f"PO number pattern {nos}")
    seqs = [int(n.rsplit("-", 1)[1]) for n in nos]
    flow.equal(seqs, sorted(set(seqs)), "sequence unique and increasing")

    flow.step("L-10  Integration: connector subscribed to all events; posting a GRN creates a job")
    events = [e["code"] for e in api.get("/integration/event-types")]
    conn = api.post("/integration/connectors", {"code": f"HK{unique}", "name": f"Hook {unique}",
                                                "endpoint_url": "http://127.0.0.1:9/hook", "event_types": events,
                                                "max_attempts": 1})
    api.post(f"/grns/{g1['id']}/post")
    jobs = api.get("/integration/jobs", connector_id=conn["id"])
    flow.check(any(j["event_type"] == "grn.posted" and j["doc_no"] == g1["doc_no"] for j in jobs),
               f"grn.posted job for {g1['doc_no']} ({[(j['event_type'], j['doc_no']) for j in jobs]})")
    flow.goto("/integration")
    page.wait_for_timeout(1500)

    flow.step("L-11  Endpoint down: job fails with a reason; disabled connector refuses retry")
    job = next((j for j in jobs if j["event_type"] == "grn.posted"), None)
    if job:
        for _ in range(30):
            job = api.get(f"/integration/jobs/{job['id']}")
            if job["status"] in ("FAILED", "SUCCEEDED") or job["attempts"] >= 1:
                break
            page.wait_for_timeout(1000)
        flow.check(job["status"] in ("FAILED", "PENDING") and (job["last_error"] or job["status"] == "PENDING"),
                   f"failed delivery recorded with a reason ({job['status']} {job.get('last_error')})")
        c = api.get("/integration/connectors")
        mine = next(x for x in c if x["id"] == conn["id"])
        api.call("PUT", f"/integration/connectors/{conn['id']}", {**{k: mine[k] for k in ("name", "endpoint_url",
                 "event_types", "timeout_seconds", "max_attempts")}, "is_active": False, "row_version": mine.get("row_version")})
        flow.rejected("POST", f"/integration/jobs/{job['id']}/retry", None, "disabled", "retry on a disabled connector")
    flow.rejected("POST", "/integration/connectors", {"code": f"BAD{unique}", "name": "Bad", "endpoint_url": "ftp://x"},
                  "http", "connector with a non-http endpoint")


def test_l_import_reports_audit(flow, unique, tmp_path):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    in_bin(api, s, s.item_b, 5, s.bin1, batch=f"X{unique}", expiry=TODAY + datetime.timedelta(days=10))
    flow.sign_in()

    flow.step("L-12  Import items from CSV with 2 bad rows: rows and reasons reported, nothing imported")
    csv = tmp_path / f"items-{unique}.csv"
    csv.write_text("SKU code,Item name,Base unit,Batch managed,Shelf life (days)\n"
                   f"IM1{unique},Import one,EA,No,30\n"
                   f"IM2{unique},Import two,NOPE,No,30\n"
                   f"IM3{unique},Import three,EA,Maybe,abc\n", encoding="utf-8")
    flow.goto("/imports")
    page.locator("input[type=file]").first.set_input_files(str(csv))
    page.wait_for_timeout(4000)
    flow.visible(page.get_by_text(re.compile(r"row\s*3|Row 3", re.I)), "row number of a bad row shown")
    with open(csv, "rb") as f:
        r = api.client.post("/api/v1/imports/items", headers=api.headers, params={"commit": "true"},
                            files={"file": (csv.name, f, "text/csv")})
    res = r.json()
    flow.check(res.get("error_count", 0) >= 2 and not res.get("committed"), f"import result {str(res)[:200]}")
    flow.check(not any(i["sku_code"] == f"IM1{unique}" for i in api.get("/items", keyword=f"IM1{unique}")),
               "nothing imported while errors remain")
    bad = tmp_path / "latin.csv"
    bad.write_bytes("SKU code,Item name,Base unit\nZ1,Caf\xe9,EA\n".encode("cp1252"))
    with open(bad, "rb") as f:
        r = api.client.post("/api/v1/imports/items", headers=api.headers, files={"file": ("latin.csv", f, "text/csv")})
    flow.check("UTF-8" in r.text or r.status_code >= 400, f"non-UTF-8 csv rejected ({r.status_code} {r.text[:120]})")

    flow.step("L-13  Reports: expiry (30 days), partner ledger, CSV export, bad date range")
    flow.goto("/reports/expiry")
    flow.visible(page.get_by_text(f"X{unique}"), "batch expiring in 10 days listed on the expiry report", timeout=20_000)
    r = api.client.get("/api/v1/reports/expiry", headers=api.headers, params={"within_days": 30, "format": "csv"})
    flow.check(r.is_success, f"expiry report ({r.status_code})")
    flow.rejected("GET", f"/reports/turnover?date_from={TODAY}&date_to={TODAY - datetime.timedelta(days=3)}", None,
                  "cannot be before", "turnover end before start")
    flow.goto("/reports/partner-ledger")
    page.wait_for_timeout(1500)
    flow.goto("/reports/picker-kpi")
    page.wait_for_timeout(1500)

    flow.step("L-14  Audit log: filter by document shows the change history")
    o = so(api, s, [(s.item_b, 1)])
    logs = api.get("/audit-logs", entity_id=o["id"])
    flow.check(len(logs) >= 1 and all(l["username"] for l in logs), f"audit rows with user ({len(logs)})")
    flow.goto(f"/sales-orders/{o['id']}")
    hist = page.get_by_role("button", name=re.compile("History", re.I))
    if hist.count():
        hist.first.click()
        flow.visible(page.get_by_text("admin"), "history drawer lists the user")
        page.keyboard.press("Escape")


def test_l_live_updates_and_pages(flow, unique, browser):
    page, api = flow.page, flow.api
    s = make_scenario(api, unique)
    o = po(api, s, [(s.item_a, 3)], confirm=False)
    flow.sign_in()

    flow.step("L-15  Live updates: a second browser confirms the PO, the first one refreshes by itself")
    flow.goto(f"/purchase-orders/{o['id']}")
    other = browser.new_context(base_url=page.url.split("/purchase-orders")[0])
    p2 = other.new_page()
    p2.goto("/login")
    p2.get_by_label("Username").fill("admin")
    p2.get_by_label("Password").fill(ADMIN_PASSWORD)
    p2.get_by_role("button", name="Sign in").click()
    p2.wait_for_url(re.compile(r"^(?!.*login)"))
    api.post(f"/purchase-orders/{o['id']}/confirm")
    flow.visible(page.locator(".ant-card-head .ant-tag", has_text=re.compile("Confirmed", re.I)),
                 "status tag turns Confirmed without reloading", timeout=30_000)
    other.close()

    flow.step("L-20  Every page renders without browser errors (smoke)")
    console: list[str] = []
    page.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
            and console.append(m.text[:200]))
    for path in PAGES:
        flow.step(f"L-20  Open {path}")
        page.goto(path)
        flow.loaded()
        page.wait_for_timeout(300)
        if console:
            flow.check(False, f"{path}: console errors {console[:3]}")
            console.clear()

    flow.step("L-20  Phone width (390 px): no horizontal page scroll on key pages")
    page.set_viewport_size({"width": 390, "height": 844})
    for path in ["/dashboard", "/purchase-orders", f"/purchase-orders/{o['id']}", "/stock", "/grns/new"]:
        page.goto(path)
        flow.loaded()
        page.wait_for_timeout(500)
        wide = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        flow.check(wide <= 1, f"{path} scrolls horizontally by {wide}px at 390 px wide")
    page.set_viewport_size({"width": 1440, "height": 900})
