"""Health checks, login and permission enforcement."""

from tests.conftest import login
from tests.helpers import Api


def test_health(client):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200


def test_login_rejects_wrong_password(client):
    response = client.post("/api/v1/auth/login", data={"username": "admin", "password": "wrong-password"})
    assert response.status_code == 401


def test_endpoints_require_a_token(client):
    assert client.get("/api/v1/items").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/api/v1/items", headers=bad).status_code == 401


def test_me_returns_admin_permissions(client, admin_headers):
    me = Api(client, admin_headers).get("/auth/me")
    assert me["username"] == "admin"
    assert "item.create" in me["permissions"]


def test_user_without_roles_is_forbidden(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    password = "Clerk@Test123"
    admin.post("/users", {"username": f"clerk{unique}", "display_name": "Clerk", "password": password})
    ea = next(u["id"] for u in admin.get("/uoms") if u["code"] == "EA")

    clerk = Api(client, login(client, f"clerk{unique}", password))
    clerk.call("POST", "/items", {"sku_code": f"X{unique}", "name": "x", "base_uom_id": ea}, expect=403)


def test_deactivated_user_is_rejected_immediately(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    password = "Temp@Test123"
    user = admin.post("/users", {"username": f"temp{unique}", "display_name": "Temp", "password": password})
    headers = login(client, f"temp{unique}", password)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    admin.call("PUT", f"/users/{user['id']}", {"display_name": "Temp", "is_active": False})
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
