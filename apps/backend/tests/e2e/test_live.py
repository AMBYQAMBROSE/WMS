"""Live updates end to end: the event stream over real HTTP, and pages refreshing by themselves."""

import json
import time

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_item, make_warehouse


def test_event_stream_over_http(base_url, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    with httpx.stream("GET", f"{base_url}/api/v1/events/stream", headers=admin_headers, timeout=20) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.iter_lines()
        assert next(line for line in lines if line.startswith("event:")) == "event: ready"

        item = make_item(api, wh, f"SSE{unique}")
        deadline = time.time() + 10
        for line in lines:
            assert time.time() < deadline, "no event within 10 s"
            if line.startswith("data: ") and item in line:
                event = next(e for e in json.loads(line[6:]) if e["id"] == item)
                assert (event["type"], event["action"]) == ("item", "CREATE")
                break


def test_event_stream_requires_sign_in(base_url):
    assert httpx.get(f"{base_url}/api/v1/events/stream", timeout=10).status_code == 401


def test_list_updates_without_reload(page: Page, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    sign_in(page)
    page.goto("/items")
    expect(page.get_by_role("status", name="Live updates: Live")).to_be_visible(timeout=10_000)

    make_item(api, wh, f"LIVE{unique}")  # someone else, e.g. another user or an import
    expect(page.get_by_role("cell", name=f"LIVE{unique}", exact=True)).to_be_visible(timeout=10_000)


def test_tabs_share_one_stream(page: Page, unique):
    """Counts streams open at the same time: development builds mount effects twice (React StrictMode), so the first
    stream of a tab is opened and aborted right away"""
    open_streams: set = set()
    is_stream = lambda r: "/events/stream" in r.url  # noqa: E731
    page.context.on("request", lambda r: is_stream(r) and open_streams.add(r))
    page.context.on("requestfailed", lambda r: open_streams.discard(r))
    page.context.on("requestfinished", lambda r: open_streams.discard(r))
    sign_in(page)
    second = page.context.new_page()
    second.goto("/dashboard")
    for tab in (page, second):
        expect(tab.get_by_role("status", name="Live updates: Live")).to_be_visible(timeout=10_000)
    page.wait_for_timeout(4_000)  # longer than a lease renewal: no second leader appears
    assert len(open_streams) == 1
