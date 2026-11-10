"""Recorded end-to-end flow tests (docs/e2e-test-checklist.md), one file per batch.

Run a batch with a video per test, slowed down so it can be watched:
    pytest tests/e2e/flows/test_batch1_golden_path.py --video on --slowmo 150 --output ../../test-recordings/batch1

Each step shows a caption at the bottom of the page, so the video says which checklist case it is on.
Checks are "soft": a failed check is recorded as an issue and the flow continues, so one run lists every
problem it meets; the test fails at the end with the whole list (also appended to test-recordings/ISSUES.md).
"""

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import ADMIN_PASSWORD
from tests.helpers import Api

ROOT = Path(__file__).resolve().parents[5]
ISSUES_FILE = Path(os.environ.get("FLOW_ISSUES_FILE") or ROOT / "test-recordings" / "ISSUES.md")

_CAPTION_SCRIPT = """
(() => {
  const show = () => {
    const text = sessionStorage.getItem('__flow_step');
    if (!text || !document.body) return;
    let el = document.getElementById('__flow_caption');
    if (!el) {
      el = document.createElement('div');
      el.id = '__flow_caption';
      el.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;pointer-events:none;' +
        'background:rgba(20,20,30,.86);color:#fff;font:600 14px/1.4 system-ui,sans-serif;padding:8px 12px;' +
        'border-radius:8px;max-width:70vw;box-shadow:0 2px 10px rgba(0,0,0,.3)';
      document.body.appendChild(el);
    }
    el.textContent = text;
  };
  window.__flowShow = show;
  document.addEventListener('DOMContentLoaded', show);
  show();
})();
"""


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    size = {"width": 1440, "height": 900}
    return {**browser_context_args, "viewport": size, "record_video_size": size}


@dataclass
class Flow:
    page: Page
    api: Api
    test_name: str
    issues: list[str] = field(default_factory=list)
    current: str = ""

    # ---- narration -------------------------------------------------------------------------------------------
    def step(self, text: str) -> None:
        self.current = text
        self.page.evaluate(
            "t => { sessionStorage.setItem('__flow_step', t); window.__flowShow && window.__flowShow(); }", text
        )

    # ---- soft checks -----------------------------------------------------------------------------------------
    def check(self, condition: bool, what: str) -> bool:
        if not condition:
            self.issues.append(f"[{self.current}] {what}")
        return bool(condition)

    def equal(self, actual, expected, what: str) -> bool:
        return self.check(actual == expected, f"{what}: expected {expected!r}, got {actual!r}")

    def visible(self, locator, what: str, timeout: int = 15_000) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:  # noqa: BLE001
            self.issues.append(f"[{self.current}] not shown: {what}")
            return False

    def attempt(self, what: str, fn, *args, **kwargs):
        """Run a UI action; a Playwright timeout/assertion becomes an issue instead of ending the run"""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001  any failure of the step is the finding
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            self.issues.append(f"[{self.current}] {what}: {first[:300]}")
            return None

    def rejected(self, method: str, path: str, body: dict | None, contains: str, what: str) -> None:
        """The API must refuse the request (4xx) with a message containing `contains`"""
        response = self.api.client.request(method, "/api/v1" + path, json=body, headers=self.api.headers)
        if response.is_success:
            self.issues.append(f"[{self.current}] {what}: was accepted ({response.status_code}), expected a rejection")
            return
        if response.status_code >= 500:
            self.issues.append(f"[{self.current}] {what}: server error {response.status_code} {response.text[:200]}")
            return
        if contains.lower() not in response.text.lower():
            self.issues.append(f"[{self.current}] {what}: rejected with {response.text[:250]!r}, expected {contains!r}")

    # ---- UI helpers ------------------------------------------------------------------------------------------
    def sign_in(self, username: str = "admin", password: str = ADMIN_PASSWORD) -> None:
        page = self.page
        page.goto("/login")
        page.get_by_label("Username").fill(username)
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Sign in").click()
        expect(page).not_to_have_url(re.compile(r"/login"), timeout=15_000)
        self.loaded()

    def sign_out(self) -> None:
        self.page.evaluate("() => { localStorage.clear(); }")
        self.page.context.clear_cookies()

    def loaded(self) -> None:
        """Wait for spinners/skeletons to go; a page still loading after 15 s is an issue, but the run waits on (90 s)"""
        busy = self.page.locator(".ant-spin-spinning, .ant-skeleton-active")
        try:
            expect(busy).to_have_count(0, timeout=15_000)
        except AssertionError:
            path = self.page.url.split("://", 1)[-1].split("/", 1)[-1]
            self.issues.append(f"[{self.current}] page /{path} still loading after 15 s")
            expect(busy).to_have_count(0, timeout=90_000)

    def goto(self, path: str) -> None:
        self.page.goto(path)
        self.loaded()

    def choose(self, target, text: str) -> None:
        """Type into a select (or the select a label points to) and take the first match with Enter, like a scanner"""
        select = self.page.get_by_label(target, exact=True) if isinstance(target, str) else target
        select.click()
        self.page.keyboard.type(text, delay=20)
        # Wait for the search result in the open dropdown and click it (the server search can be slow)
        option = self.page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option",
                                   has_text=text).first
        try:
            option.wait_for(state="visible", timeout=20_000)
            option.click()
        except Exception:  # noqa: BLE001
            self.issues.append(f"[{self.current}] no option matching {text!r} appeared in the dropdown")
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(200)

    def choose_in(self, container, text: str) -> None:
        """Select inside a container (table cell, modal) without a label"""
        self.choose(container.locator(".ant-select").first, text)

    def pick_date(self, container, value: datetime.date) -> None:
        picker = container.locator(".ant-picker input").first
        picker.click()
        picker.fill(value.isoformat())
        picker.press("Enter")

    def confirm_action(self, label: str) -> None:
        """Click a document action button and accept its confirmation"""
        self.page.get_by_role("button", name=label, exact=True).first.click()
        self.page.locator(".ant-popover:visible, .ant-popconfirm:visible").get_by_role("button", name="OK").click()

    def toast_error(self, timeout: int = 8_000) -> str | None:
        toast = self.page.locator(".ant-message-error").last
        try:
            toast.wait_for(state="visible", timeout=timeout)
        except Exception:  # noqa: BLE001
            return None
        return toast.inner_text().strip()

    def expect_rejected(self, contains: str, what: str) -> None:
        text = self.toast_error()
        if text is None:
            self.issues.append(f"[{self.current}] {what}: no error was shown (expected one containing {contains!r})")
        elif contains.lower() not in text.lower():
            self.issues.append(f"[{self.current}] {what}: error shown was {text!r}, expected it to contain {contains!r}")
        self.page.evaluate("() => document.querySelectorAll('.ant-message-notice').forEach(n => n.remove())")

    def status_of(self) -> str:
        """Status tag in the document title"""
        return self.page.locator(".ant-card-head .ant-tag").first.inner_text().strip()

    def wait_doc(self, path: str) -> str:
        """Wait until the browser is on /<path>/<uuid> (after a save) and return the id"""
        self.page.wait_for_url(re.compile(rf"/{path}/[0-9a-f]{{8}}-[0-9a-f-]{{27}}($|[?#])"), timeout=15_000)
        self.loaded()
        return self.doc_id()

    def saved(self, path: str, fallback, what: str) -> str:
        """After clicking Save/Create: the id of the new document. If the UI fails to create it, record the issue
        (with the error the user saw), create it through the API instead and open it, so the flow can go on."""
        try:
            return self.wait_doc(path)
        except Exception:  # noqa: BLE001
            shown = self.toast_error(timeout=1_000)
            self.issues.append(f"[{self.current}] {what} failed in the UI; error shown: {shown!r} (continued via API)")
            doc = fallback()
            self.goto(f"/{path}/{doc['id']}")
            return doc["id"]

    def doc_id(self) -> str:
        return self.page.url.rstrip("/").split("/")[-1].split("?")[0]

    def wait_status(self, path: str, doc_id: str, status: str, timeout_s: float = 10) -> str:
        import time

        deadline = time.time() + timeout_s
        current = None
        while time.time() < deadline:
            current = self.api.get(f"/{path}/{doc_id}")["status"]
            if current == status:
                return current
            time.sleep(0.3)
        return current


def _record(test_name: str, issues: list[str]) -> None:
    ISSUES_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with ISSUES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n### {test_name}  ({stamp})\n\n")
        for issue in issues:
            f.write(f"- {issue}\n")


@pytest.fixture
def flow(page: Page, client, admin_headers, request) -> Flow:
    page.context.add_init_script(_CAPTION_SCRIPT)
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"browser error: {exc}"))
    f = Flow(page=page, api=Api(client, admin_headers), test_name=request.node.name)

    def on_response(response):
        if response.status >= 400 and "/api/" in response.url:
            try:
                body = response.text()[:400]
            except Exception:  # noqa: BLE001
                body = ""
            sent = (response.request.post_data or "")[:400]
            line = f"{response.request.method} {response.url.split('/api/v1')[-1]} -> {response.status} {body} | sent {sent}"
            print("API-ERROR", line)
            if response.status >= 500:
                errors.append(f"server error during [{f.current}]: {line}")

    page.on("response", on_response)
    yield f
    issues = f.issues + errors
    if issues:
        _record(request.node.nodeid, issues)
        pytest.fail(f"{len(issues)} issue(s):\n" + "\n".join(issues), pytrace=False)


def db_session():
    from app.core.db import SessionLocal

    return SessionLocal()


def add_conversion(item_id: str, from_uom_id: str, to_uom_id: str, factor: float) -> None:
    """No API exists for unit conversions (see ISSUES.md), so tests write them directly"""
    import uuid

    from app.models.item import Item, ItemUomConversion

    with db_session() as db:
        item = db.get(Item, uuid.UUID(item_id))
        db.add(ItemUomConversion(
            tenant_id=item.tenant_id, item_id=item.id, from_uom_id=uuid.UUID(from_uom_id),
            to_uom_id=uuid.UUID(to_uom_id), factor=factor, created_by=item.created_by, updated_by=item.created_by,
        ))
        db.commit()


def dump(obj) -> str:
    return json.dumps(obj, default=str, indent=1)
