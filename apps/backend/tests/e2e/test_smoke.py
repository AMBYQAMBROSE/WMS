"""Smoke test of the web console: sign in, open every page, and fail on any runtime error in the browser."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.conftest import ADMIN_PASSWORD

PAGES = [
    "/dashboard", "/reports/turnover", "/reports/picker-kpi", "/reports/expiry", "/reports/partner-ledger",
    "/purchase-orders", "/purchase-orders/new", "/grns", "/grns/new", "/putaways", "/putaways/new",
    "/sales-orders", "/sales-orders/new", "/picks", "/shipments", "/shortages",
    "/stock", "/moves", "/moves/new", "/adjustments", "/adjustments/new", "/cycle-counts", "/cycle-counts/new",
    "/repacks", "/returns-in", "/returns-out", "/returnable-assets",
    "/business-partners", "/items", "/locations", "/reason-codes",
    "/users", "/roles", "/features", "/integration", "/imports",
]

# Expected noise: the browser logs every non-2xx response (e.g. a disabled feature answering 403)
_IGNORED = re.compile(r"Failed to load resource")


@pytest.fixture
def errors(page: Page) -> list[str]:
    collected: list[str] = []
    page.on("pageerror", lambda exc: collected.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: msg.type == "error" and not _IGNORED.search(msg.text) and collected.append(f"console: {msg.text}"),
    )
    return collected


def sign_in(page: Page) -> None:
    page.goto("/login")
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    expect(page).not_to_have_url(re.compile(r"/login"))


def test_wrong_password_shows_an_error(page: Page, errors):
    page.goto("/login")
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Incorrect username or password")).to_be_visible()


def test_every_page_renders_without_errors(page: Page, errors):
    sign_in(page)
    for path in PAGES:
        page.goto(path)
        page.wait_for_load_state("networkidle")
        expect(page.locator("main, .ant-layout-content").first).to_be_visible()
        assert not errors, f"{path}: {errors}"


def test_command_palette_jumps_to_a_page(page: Page, errors):
    sign_in(page)
    page.keyboard.press("Control+k")
    page.get_by_placeholder("Jump to a page…").fill("Items")
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"/items$"))
    assert not errors
