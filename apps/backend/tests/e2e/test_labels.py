"""Labels in the browser: set up a label layout, test-print it, and print item and location labels."""

import os

from playwright.sync_api import Page, expect

from tests.e2e.test_smoke import sign_in
from tests.helpers import Api

# Optional: where to save screenshots of the label screens for a visual check
SHOTS = os.environ.get("E2E_SCREENSHOTS")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"))


def expect_pdf_preview(page: Page, click=None, method: str = "POST", tabs: list[str] | None = None, shot_as: str | None = None) -> None:
    """A PDF is fetched and shown in the print preview, with Print ready to click; the preview is then closed.
    `click`: what brings it up (nothing when it opens by itself); `tabs`: the PDFs expected in it, when several.
    (Headless Chromium has no PDF viewer, so what the frame shows is not checked.)"""
    def is_pdf_request(r) -> bool:
        return r.request.method == method and "/api/v1/" in r.url and ("/print" in r.url or "label" in r.url)

    if click:
        with page.expect_response(is_pdf_request) as response:
            click()
        assert response.value.status == 200, response.value.text()
        assert response.value.headers["content-type"] == "application/pdf"
        assert response.value.body().startswith(b"%PDF")
    expect(page.get_by_test_id("print-preview-print")).to_be_visible()
    expect(page.get_by_test_id("print-preview-print")).to_be_focused()
    for name in tabs or []:
        expect(page.get_by_role("tab", name=name)).to_be_visible()
    expect(page.get_by_test_id("print-preview-frame")).to_have_count(len(tabs) if tabs else 1)
    if shot_as:
        shot(page, shot_as)
    page.locator(".wms-print-footer").get_by_role("button", name="Close").click()
    expect(page.get_by_test_id("print-preview-print")).to_be_hidden()


def test_label_layout_set_up_and_test_print(page: Page, errors, unique):
    sign_in(page)
    page.goto("/label-settings")
    page.get_by_test_id("new-label-profile").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Name", exact=True).fill(f"Roll {unique}")
    dialog.get_by_role("combobox", name="Start from label stock").click()
    page.get_by_title("Thermal roll, 50 × 30 mm").click()
    expect(dialog.get_by_text("One 50 × 30 mm label per page")).to_be_visible()
    dialog.get_by_text("Sheet of labels (office printer)").click()
    dialog.get_by_label("Labels across").fill("4")
    dialog.get_by_label("Labels down").fill("9")
    expect(dialog.get_by_text("36 labels per page")).to_be_visible()
    shot(page, "label-editor")
    expect_pdf_preview(page, lambda: dialog.get_by_test_id("label-test-print").click())
    dialog.get_by_test_id("label-save").click()
    expect(page.get_by_role("cell", name=f"Roll {unique}", exact=True)).to_be_visible()
    shot(page, "label-settings")
    assert not errors


def test_print_item_and_location_labels(page: Page, errors, client, admin_headers, unique):
    api = Api(client, admin_headers)
    ea = next(u["id"] for u in api.get("/uoms") if u["code"] == "EA")
    api.post("/items", {"sku_code": f"PL{unique}", "name": "Label print item", "base_uom_id": ea})
    wh = api.post("/locations", {"code": f"PW{unique}", "name": "Print warehouse", "location_type": "WAREHOUSE"})
    api.post("/locations", {"code": f"PB{unique}", "name": "Print bin", "location_type": "BIN", "parent_id": wh["id"]})

    sign_in(page)
    page.goto("/items")
    page.get_by_placeholder("SKU / name / barcode").fill(f"PL{unique}")
    page.keyboard.press("Enter")
    row = page.get_by_role("row").filter(has_text=f"PL{unique}")
    row.get_by_role("checkbox").check()
    page.get_by_role("button", name="Print labels (1)").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_test_id("label-copies").fill("3")
    shot(page, "item-print")
    expect_pdf_preview(page, lambda: dialog.get_by_role("button", name="Print").click())
    expect(dialog).to_be_hidden()

    page.goto("/locations")
    page.get_by_test_id("print-location-labels").click()
    page.get_by_text("Every bin and dock in an area…").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Area").fill(f"PW{unique}")
    page.get_by_title(f"PW{unique} Print warehouse").click()
    expect_pdf_preview(page, lambda: dialog.get_by_role("button", name="Print").click())
    assert not errors
