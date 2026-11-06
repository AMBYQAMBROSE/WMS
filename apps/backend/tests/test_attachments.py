"""Photos on documents: storage, type checks, permissions that follow the document, and safe retries."""

import base64

from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse, receive

# Smallest bytes the server accepts as JPEG: it checks the file signature, it does not decode the image
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _grn(api: Api, unique: str) -> dict:
    wh = make_warehouse(api, unique)
    return receive(api, wh, make_item(api, wh, f"AT{unique}"), 2)


def test_photo_is_stored_and_served(client, admin_headers, unique):
    api = Api(client, admin_headers)
    grn = _grn(api, unique)
    added = api.post(f"/documents/{grn['id']}/attachments", {"content_base64": _b64(JPEG), "caption": "Crushed carton"})
    assert (added["content_type"], added["size_bytes"], added["caption"], added["created_by"]) == ("image/jpeg", len(JPEG), "Crushed carton", "admin")
    assert added["file_name"].startswith(grn["doc_no"])

    assert [a["id"] for a in api.get(f"/documents/{grn['id']}/attachments")] == [added["id"]]
    content = client.get(f"/api/v1/attachments/{added['id']}/content", headers=admin_headers)
    assert content.status_code == 200
    assert content.content == JPEG
    assert content.headers["content-type"] == "image/jpeg"
    assert content.headers["x-content-type-options"] == "nosniff"


def test_photo_is_in_the_document_history_without_its_bytes(client, admin_headers, unique):
    api = Api(client, admin_headers)
    grn = _grn(api, unique)
    added = api.post(f"/documents/{grn['id']}/attachments", {"content_base64": _b64(PNG)})
    entry = next(e for e in api.get("/audit-logs", entity_id=grn["id"]) if e["entity_type"] == "document_attachment")
    assert entry["entity_label"] == added["file_name"]
    fields = {c["field"] for c in entry["changes"]}
    assert "content" not in fields and "size_bytes" in fields


def test_only_images_are_accepted(client, admin_headers, unique):
    api = Api(client, admin_headers)
    grn = _grn(api, unique)
    for data in (b"%PDF-1.7 not a photo", b"<html><script>alert(1)</script></html>"):
        api.call("POST", f"/documents/{grn['id']}/attachments", {"content_base64": _b64(data)}, expect=400)
    api.call("POST", f"/documents/{grn['id']}/attachments", {"content_base64": "not base64!!"}, expect=400)
    assert api.get(f"/documents/{grn['id']}/attachments") == []


def test_permissions_follow_the_document(client, admin_headers, unique):
    admin = Api(client, admin_headers)
    grn = _grn(admin, unique)
    role = admin.post("/roles", {"code": f"GR{unique}", "name": "GRN viewer", "permission_codes": ["grn.read"]})
    admin.post("/users", {"username": f"gv{unique}", "display_name": "V", "password": "View@Test123", "role_codes": [role["code"]]})
    admin.post("/users", {"username": f"nv{unique}", "display_name": "N", "password": "None@Test123"})
    viewer = Api(client, login(client, f"gv{unique}", "View@Test123"))
    nobody = Api(client, login(client, f"nv{unique}", "None@Test123"))

    added = admin.post(f"/documents/{grn['id']}/attachments", {"content_base64": _b64(JPEG)})
    assert len(viewer.get(f"/documents/{grn['id']}/attachments")) == 1
    viewer.call("POST", f"/documents/{grn['id']}/attachments", {"content_base64": _b64(JPEG)}, expect=403)
    viewer.call("DELETE", f"/attachments/{added['id']}", expect=403)
    # Without read access the document does not exist for them
    nobody.call("GET", f"/documents/{grn['id']}/attachments", expect=404)
    nobody.call("GET", f"/attachments/{added['id']}/content", expect=404)


def test_deleted_photo_is_gone(client, admin_headers, unique):
    api = Api(client, admin_headers)
    grn = _grn(api, unique)
    added = api.post(f"/documents/{grn['id']}/attachments", {"content_base64": _b64(JPEG)})
    api.call("DELETE", f"/attachments/{added['id']}")
    assert api.get(f"/documents/{grn['id']}/attachments") == []
    api.call("GET", f"/attachments/{added['id']}/content", expect=404)


def test_retried_upload_with_the_same_key_stores_one_photo(client, admin_headers, unique):
    """The PDA sends each queued photo with its own Idempotency-Key, so a retry after a lost response adds nothing"""
    api = Api(client, admin_headers)
    grn = _grn(api, unique)
    headers = {**admin_headers, "Idempotency-Key": f"photo-{unique}"}
    body = {"content_base64": _b64(JPEG), "caption": "Wet pallet"}
    first = client.post(f"/api/v1/documents/{grn['id']}/attachments", json=body, headers=headers)
    again = client.post(f"/api/v1/documents/{grn['id']}/attachments", json=body, headers=headers)
    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert len(api.get(f"/documents/{grn['id']}/attachments")) == 1
