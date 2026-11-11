"""Document reports (PDF) for every document type."""

import os

from tests.helpers import PREFIX, Api, make_item, make_warehouse, put_away, receive
from tests.test_labels import pages

# Optional: a folder to save every printed PDF in, to look at them
SAVE_TO = os.environ.get("SAVE_PDFS")


def print_doc(client, headers, document_id: str, expect: int = 200) -> bytes:
    response = client.get(f"{PREFIX}/documents/{document_id}/print", headers=headers)
    assert response.status_code == expect, response.text
    if expect == 200:
        assert response.headers["content-type"] == "application/pdf"
        assert "filename*=UTF-8''" in response.headers["content-disposition"]
        if SAVE_TO:
            name = response.headers["content-disposition"].split("''")[1]
            with open(os.path.join(SAVE_TO, name), "wb") as f:
                f.write(response.content)
    return response.content


def test_every_step_from_order_to_delivery_prints(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"RPT{unique}")
    grn = receive(api, wh, item, 10)
    putaway = put_away(api, wh, item, 10)

    so = api.post("/sales-orders", {"partner_id": wh.customer, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 7}]})
    api.post(f"/sales-orders/{so['id']}/confirm")
    pick = api.post(f"/sales-orders/{so['id']}/allocate", {"staging_location_id": wh.dock_out})["pick"]
    # An open pick list prints too: it is the paper list the picker walks with
    assert pages(print_doc(client, admin_headers, pick["id"])) == 1
    api.post(f"/picks/{pick['id']}/confirm-all")
    api.post(f"/picks/{pick['id']}/post")
    ship = api.post("/shipments", {"so_id": so["id"], "carrier": "Own fleet", "vehicle_no": "AB 1234", "driver_name": "Driver 甲"})
    api.post(f"/shipments/{ship['id']}/post")

    for doc_id in (grn["ref_document"]["id"], grn["id"], putaway["id"], so["id"], pick["id"], ship["id"]):
        assert pages(print_doc(client, admin_headers, doc_id)) == 1

    # Each print is in the document's history
    logs = api.get("/audit-logs", entity_id=ship["id"], action="PRINT")
    assert [log["action"] for log in logs] == ["PRINT"]


def test_inventory_documents_print(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"INV{unique}")
    receive(api, wh, item, 5)
    put_away(api, wh, item, 5)
    reason = next(r["id"] for r in api.get("/reason-codes", category="ADJUST"))
    adjustment = api.post("/adjustments", {"reason_code_id": reason, "lines": [{"item_id": item, "uom_id": wh.ea, "location_id": wh.bin, "qty": -2}]})
    count = api.post("/cycle-counts", {"location_ids": [wh.bin]})
    try:
        for doc_id in (adjustment["id"], count["id"]):
            assert pages(print_doc(client, admin_headers, doc_id)) == 1
    finally:
        api.post(f"/cycle-counts/{count['id']}/cancel")


def test_long_documents_continue_on_more_pages(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    lines = [{"item_id": make_item(api, wh, f"L{unique}{i:02d}"), "uom_id": wh.ea, "qty": i + 1} for i in range(70)]
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": lines, "remark": "Deliver to dock 2 before noon"})
    assert pages(print_doc(client, admin_headers, po["id"])) >= 2


def test_cancelled_and_unknown_documents(client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"CXL{unique}")
    po = api.post("/purchase-orders", {"partner_id": wh.supplier, "lines": [{"item_id": item, "uom_id": wh.ea, "qty": 1}]})
    api.post(f"/purchase-orders/{po['id']}/cancel")
    assert pages(print_doc(client, admin_headers, po["id"])) == 1
    print_doc(client, admin_headers, "00000000-0000-0000-0000-000000000000", expect=404)
