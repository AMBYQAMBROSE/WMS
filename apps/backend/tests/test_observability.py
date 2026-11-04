"""Request ids, error responses, structured logs and the system status page."""

import json
import logging

from app.core.observability import JsonFormatter
from tests.conftest import login
from tests.helpers import Api


def test_system_status(client, admin_headers):
    status = Api(client, admin_headers).get("/system/status")
    assert status["db_revision"] == status["code_revision"]
    assert status["database"]["latency_ms"] >= 0
    assert status["telemetry"]["otel_enabled"] is False
    assert status["audit_entries_24h"] >= 0
    assert set(status["integration"]) == {"pending", "running", "failed", "oldest_pending_at"}


def test_system_status_requires_permission(client, admin_headers, unique):
    Api(client, admin_headers).post("/users", {"username": f"st{unique}", "display_name": "S", "password": "Stat@Test123"})
    Api(client, login(client, f"st{unique}", "Stat@Test123")).call("GET", "/system/status", expect=403)


def test_request_id_is_generated_or_passed_through(client):
    generated = client.get("/api/v1/health").headers["x-request-id"]
    assert len(generated) == 16
    assert client.get("/api/v1/health", headers={"X-Request-ID": "from-nginx-123"}).headers["x-request-id"] == "from-nginx-123"


def test_unhandled_error_returns_request_id_and_is_logged(client, caplog):
    from app.main import app

    path = "/api/v1/_test/boom"
    if not any(getattr(r, "path", None) == path for r in app.routes):
        def boom():
            raise RuntimeError("kaboom")
        app.add_api_route(path, boom)
        # First, so the browser tests' catch-all web app mount (tests/e2e) cannot shadow it
        app.router.routes.insert(0, app.router.routes.pop())

    with caplog.at_level(logging.ERROR, logger="wms.request"):
        response = client.get(path)
    assert response.status_code == 500
    request_id = response.headers["x-request-id"]
    assert request_id in response.json()["detail"]
    assert "kaboom" not in response.text, "internals must not leak to the client"
    assert any("kaboom" in (r.exc_text or "") or "kaboom" in str(r.exc_info) for r in caplog.records)


def test_json_log_format():
    record = logging.LogRecord("wms.request", logging.INFO, __file__, 1, "GET %s", ("/x",), None)
    record.request_id, record.user, record.duration_ms = "abc123", "admin", 42
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "GET /x"
    assert (entry["request_id"], entry["user"], entry["duration_ms"]) == ("abc123", "admin", 42)
    assert entry["level"] == "INFO"
