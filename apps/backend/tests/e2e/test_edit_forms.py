"""Edit forms in the browser show the record's existing list rows (item packing units, connector headers), not empty rows."""

from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api, make_warehouse


def _uom(api: Api, code: str) -> str:
    return next(u["id"] for u in api.get("/uoms") if u["code"] == code)


def _expect_packings(page: Page, sku: str, rows: list[tuple[str, str]]):
    """Open the item's edit form and check each packing row shows its unit and quantity"""
    page.get_by_placeholder("SKU / name / barcode").fill(sku)
    page.get_by_placeholder("SKU / name / barcode").press("Enter")
    page.get_by_role("button", name=f"Edit item {sku}").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text(f"Edit item: {sku}")).to_be_visible()
    expect(dialog.get_by_label("Name", exact=True)).to_have_value(f"Item {sku}")  # plain fields are filled too
    for i, (code, qty) in enumerate(rows, start=1):
        select = dialog.locator(".ant-select").filter(has=page.get_by_label(f"Packing unit {i}", exact=True))
        expect(select.locator(".ant-select-content, .ant-select-selection-item").first).to_contain_text(code)
        expect(dialog.get_by_label(f"Base units per packing unit {i}")).to_have_value(qty)
    expect(dialog.get_by_label(f"Packing unit {len(rows) + 1}", exact=True)).to_have_count(0)
    dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()


def test_edit_form_shows_existing_packing_units(page: Page, client, admin_headers, unique):
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    ctn, plt = _uom(api, "CTN"), _uom(api, "PLT")
    one = f"PE{unique}A"
    api.post("/items", {"sku_code": one, "name": f"Item {one}", "base_uom_id": wh.ea,
                        "packings": [{"uom_id": ctn, "factor": 12}, {"uom_id": plt, "factor": 480}]})
    two = f"PE{unique}B"
    api.post("/items", {"sku_code": two, "name": f"Item {two}", "base_uom_id": wh.ea,
                        "packings": [{"uom_id": plt, "factor": 300}]})

    sign_in(page)
    page.goto("/items")
    # The new-item form opened and cancelled first leaves its own packing rows behind in the form
    page.get_by_role("button", name="New item").click()
    page.get_by_role("dialog").get_by_role("button", name="Cancel").click()
    expect(page.get_by_role("dialog")).to_be_hidden()

    _expect_packings(page, one, [("CTN", "12"), ("PLT", "480")])
    _expect_packings(page, two, [("PLT", "300")])  # one row, not the previous item's two


def test_edit_connector_shows_existing_headers(page: Page, client, admin_headers, unique):
    """The connector form's header rows are a Form.List too, and were emptied the same way"""
    api = Api(client, admin_headers)
    events = [e["code"] for e in api.get("/integration/event-types")][:1]
    code = f"HE{unique}"
    api.post("/integration/connectors", {"code": code, "name": f"Hook {unique}", "endpoint_url": "http://127.0.0.1:9/hook",
                                         "event_types": events, "extra_headers": {"Authorization": "Bearer abc"}})

    sign_in(page)
    page.goto("/integration")
    page.get_by_role("row").filter(has_text=code).get_by_role("button", name="Edit").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text(f"Edit connector {code}")).to_be_visible()
    expect(dialog.get_by_placeholder("Name", exact=True)).to_have_value("Authorization")
    expect(dialog.get_by_placeholder("Value", exact=True)).to_have_value("Bearer abc")


def test_saving_the_edit_form_keeps_and_changes_packings(page: Page, client, admin_headers, unique):
    """OK submits the modal's form: a changed quantity is saved, the untouched packing row and fields are kept"""
    api = Api(client, admin_headers)
    wh = make_warehouse(api, unique)
    ctn, plt = _uom(api, "CTN"), _uom(api, "PLT")
    sku = f"PS{unique}"
    item = api.post("/items", {"sku_code": sku, "name": f"Item {sku}", "base_uom_id": wh.ea, "category": "Dry",
                               "packings": [{"uom_id": ctn, "factor": 12}, {"uom_id": plt, "factor": 480}]})

    sign_in(page)
    page.goto("/items")
    page.get_by_placeholder("SKU / name / barcode").fill(sku)
    page.get_by_placeholder("SKU / name / barcode").press("Enter")
    page.get_by_role("button", name=f"Edit item {sku}").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_label("Base units per packing unit 1")).to_have_value("12")
    dialog.get_by_label("Base units per packing unit 1").fill("24")
    dialog.get_by_role("button", name="OK").click()
    expect(page.get_by_text("Saved")).to_be_visible()
    expect(dialog).to_be_hidden()

    saved = api.get(f"/items/{item['id']}")
    assert [(p["uom"]["code"], p["factor"]) for p in saved["packings"]] == [("CTN", 24), ("PLT", 480)]
    assert (saved["name"], saved["category"]) == (f"Item {sku}", "Dry")
