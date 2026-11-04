"""Browser tests: the built web app and the API served from one in-process server on the test database.

Build the web app first (cd apps/web && npm run build), or point WEB_DIST at another build, e.g. a development
build so React and antd runtime warnings show up as console errors:
    npx vite build --mode development --outDir <dir>
Skipped when the build or Playwright is missing; run only these with: pytest tests/e2e
"""

import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")

WEB_DIST = Path(os.environ.get("WEB_DIST") or Path(__file__).resolve().parents[4] / "apps" / "web" / "dist")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(database) -> str:
    """Overrides pytest-playwright's base_url, so page.goto("/login") hits this server"""
    if not (WEB_DIST / "index.html").exists():
        pytest.skip(f"web build not found at {WEB_DIST}")

    import uvicorn
    from starlette.exceptions import HTTPException
    from starlette.responses import FileResponse
    from starlette.staticfiles import StaticFiles

    from app.main import app

    class SpaFiles(StaticFiles):
        """Unknown paths fall back to index.html, like nginx try_files in production"""

        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                return FileResponse(WEB_DIST / "index.html")

    # Mounted last so every /api route registered on the app wins
    if not any(getattr(route, "name", None) == "web" for route in app.routes):
        app.mount("/", SpaFiles(directory=WEB_DIST, html=True), name="web")

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
