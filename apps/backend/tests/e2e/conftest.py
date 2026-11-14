"""Browser tests: a built front end and the API served from one in-process server on the test database.

- Web console (base_url): build it first (cd apps/web && npm run build), or point WEB_DIST at another build, e.g. a
  development build so React and antd runtime warnings show up as console errors:
      npx vite build --mode development --outDir <dir>
- PDA app in its browser build (pda_url): cd apps/mobile && npx expo export --platform web, or point PDA_DIST at it.
  The camera, scanner hardware and vibration are not available there; screens, the offline queue and uploads are.
Tests whose build is missing are skipped; run only these with: pytest tests/e2e
"""

import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")

APPS = Path(__file__).resolve().parents[4] / "apps"
WEB_DIST = Path(os.environ.get("WEB_DIST") or APPS / "web" / "dist")
PDA_DIST = Path(os.environ.get("PDA_DIST") or APPS / "mobile" / "dist")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spa(dist: Path):
    """Static files where unknown paths fall back to index.html, like nginx try_files in production"""
    from starlette.exceptions import HTTPException
    from starlette.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    class SpaFiles(StaticFiles):
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                return FileResponse(dist / "index.html")

    return SpaFiles(directory=dist, html=True)


def _with_front_end(dist: Path):
    """/api goes to the backend, everything else to the front end's files"""
    from app.main import app

    files = _spa(dist)

    async def asgi(scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith("/api/"):
            await files(scope, receive, send)
        else:
            await app(scope, receive, send)

    return asgi


def _serve(asgi):
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(asgi, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session")
def base_url(database) -> str:
    """Web console. Overrides pytest-playwright's base_url, so page.goto("/login") hits this server"""
    if not (WEB_DIST / "index.html").exists():
        pytest.skip(f"web build not found at {WEB_DIST}")
    server, thread, url = _serve(_with_front_end(WEB_DIST))
    yield url
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def pda_url(database) -> str:
    """PDA app (browser build) with the API on the same origin, so its server URL is <pda_url>/api/v1"""
    if not (PDA_DIST / "index.html").exists():
        pytest.skip(f"PDA web build not found at {PDA_DIST}")
    server, thread, url = _serve(_with_front_end(PDA_DIST))
    yield url
    server.should_exit = True
    thread.join(timeout=10)


# Expected noise: the browser logs every non-2xx response (e.g. a disabled feature answering 403)
_IGNORED = re.compile(r"Failed to load resource")


@pytest.fixture(autouse=True)
def _print_preview_stays_closed(request, context):
    """Posting a document opens its printout over the page. Tests that go on clicking after a post switch that off, as
    a user can with the preview's checkbox; a test module about printing sets PRINT_PREVIEW = True to keep it."""
    if getattr(request.module, "PRINT_PREVIEW", False):
        return
    context.add_init_script(
        """try {
            const saved = JSON.parse(localStorage.getItem("wms-ui") || '{"state":{},"version":1}');
            saved.state.printAfterPosting = false;
            localStorage.setItem("wms-ui", JSON.stringify(saved));
        } catch {}"""
    )


@pytest.fixture
def errors(page) -> list[str]:
    """Browser errors (uncaught exceptions, console errors) collected while a test runs: assert it stays empty"""
    collected: list[str] = []
    page.on("pageerror", lambda exc: collected.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: msg.type == "error" and not _IGNORED.search(msg.text) and collected.append(f"console: {msg.text}"),
    )
    return collected
