"""Idempotency-Key: a retried POST is answered from the first execution, never executed twice."""

import threading

from fastapi.testclient import TestClient

from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse


def _order(api: Api, unique: str) -> tuple[dict, str]:
    wh = make_warehouse(api, unique)
    body = {"partner_id": wh.supplier, "remark": f"idem-{unique}",
            "lines": [{"item_id": make_item(api, wh, f"IK{unique}"), "uom_id": wh.ea, "qty": 3}]}
    return body, f"idem-{unique}"


def _count(api: Api, remark: str) -> int:
    return len(api.get("/purchase-orders", keyword=remark))


def test_retry_replays_the_first_response(client, admin_headers, unique):
    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    headers = {**admin_headers, "Idempotency-Key": f"k-{unique}"}

    first = client.post("/api/v1/purchase-orders", json=body, headers=headers)
    retry = client.post("/api/v1/purchase-orders", json=body, headers=headers)
    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json()
    assert retry.headers.get("idempotent-replayed") == "true"
    assert "idempotent-replayed" not in first.headers
    assert _count(api, remark) == 1


def test_without_a_key_nothing_changes(client, admin_headers, unique):
    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    for _ in range(2):
        assert client.post("/api/v1/purchase-orders", json=body, headers=admin_headers).status_code == 201
    assert _count(api, remark) == 2


def test_key_reused_for_a_different_request_is_refused(client, admin_headers, unique):
    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    headers = {**admin_headers, "Idempotency-Key": f"k-{unique}"}
    assert client.post("/api/v1/purchase-orders", json=body, headers=headers).status_code == 201
    changed = {**body, "remark": f"{remark}-other"}
    response = client.post("/api/v1/purchase-orders", json=changed, headers=headers)
    assert response.status_code == 400
    assert "different request" in response.json()["detail"]


def test_failed_request_can_be_retried_with_its_key(client, admin_headers, unique):
    """A failure rolls the key back with everything else: the retry runs again instead of replaying the failure"""
    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    wh_customer_only = api.post("/business-partners", {"code": f"CO{unique}", "name": "Customer", "partner_type": "customer"})
    bad = {**body, "partner_id": wh_customer_only["id"]}  # not a supplier: refused by the service
    headers = {**admin_headers, "Idempotency-Key": f"k-{unique}"}
    for _ in range(2):
        response = client.post("/api/v1/purchase-orders", json=bad, headers=headers)
        assert response.status_code == 400, response.text
        assert "idempotent-replayed" not in response.headers


def test_keys_are_per_user(client, admin_headers, unique):
    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    api.post("/users", {"username": f"ik{unique}", "display_name": "K", "password": "Idem@Test123", "role_codes": ["ADMIN"]})
    other = login(client, f"ik{unique}", "Idem@Test123")
    key = {"Idempotency-Key": f"shared-{unique}"}
    assert client.post("/api/v1/purchase-orders", json=body, headers={**admin_headers, **key}).status_code == 201
    response = client.post("/api/v1/purchase-orders", json=body, headers={**other, **key})
    assert response.status_code == 201 and "idempotent-replayed" not in response.headers
    assert _count(api, remark) == 2


def test_simultaneous_duplicates_create_one_order(client, admin_headers, unique):
    """The duplicate waits on the key's lock while the original runs, then replays it"""
    from app.main import app

    api = Api(client, admin_headers)
    body, remark = _order(api, unique)
    headers = {**admin_headers, "Idempotency-Key": f"race-{unique}"}
    responses = []

    def send():
        with TestClient(app) as own_client:  # its own event loop thread, so the requests really overlap
            responses.append(own_client.post("/api/v1/purchase-orders", json=body, headers=headers))

    threads = [threading.Thread(target=send) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert [r.status_code for r in responses] == [201] * 4, [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert _count(api, remark) == 1


def test_overlong_key_is_refused(client, admin_headers):
    response = client.post("/api/v1/purchase-orders", json={}, headers={**admin_headers, "Idempotency-Key": "x" * 101})
    assert response.status_code == 400


def test_failed_commit_is_an_error_not_a_success(client, admin_headers, monkeypatch):
    """The transaction commits before the response is sent: a commit that fails must not follow a 2xx"""
    from fastapi import Depends
    from sqlalchemy.orm import Session

    from app.api.deps import get_db_session
    from app.api.routing import TransactionalRoute
    from app.main import app

    path = "/api/v1/_test/commit-fails"
    if not any(getattr(r, "path", None) == path for r in app.routes):
        def endpoint(db: Session = Depends(get_db_session)):
            def failing_commit():
                raise RuntimeError("commit failed")
            monkeypatch.setattr(db, "commit", failing_commit)
            return {"saved": True}

        app.router.add_api_route(path, endpoint, methods=["POST"], route_class_override=TransactionalRoute)
        app.router.routes.insert(0, app.router.routes.pop())  # ahead of the browser tests' catch-all mount

    response = client.post(path, headers=admin_headers)
    assert response.status_code == 500
    assert "saved" not in response.text
