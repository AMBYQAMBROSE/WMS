"""AI assistant page, with a scripted model in place of the AI provider (no real model is called)."""

from playwright.sync_api import Page, expect

from app.core.config import settings
from tests.e2e.test_smoke import sign_in
from tests.helpers import Api
from tests.test_assistant import reply, text, tool, use_model


def test_ask_on_the_assistant_page(page: Page, errors, client, admin_headers, unique, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    admin = Api(client, admin_headers)
    admin.call("PUT", "/features/AI_ASSISTANT", {"enabled": True})
    use_model(
        monkeypatch,
        reply(tool("expiring_stock", {"within_days": 30}), stop_reason="tool_use"),
        reply(text(f"Nothing urgent.\n\n| Batch | Days left |\n|---|---|\n| B{unique} | 12 |")),
    )
    try:
        sign_in(page)
        page.goto("/assistant")
        page.get_by_role("textbox", name="Question").fill(f"What expires soon? {unique}")
        page.get_by_role("button", name="Send").click()

        answer = page.get_by_test_id("ai-answer").last
        expect(answer.locator("table")).to_contain_text(f"B{unique}")  # Markdown table rendered as a table
        expect(page.locator(".wms-ai-tool")).to_contain_text("expiring_stock(within_days=30)")
        expect(page.get_by_role("button", name=f"What expires soon? {unique}", exact=True)).to_be_visible()  # in the conversation list

        page.reload()
        page.get_by_role("button", name=f"What expires soon? {unique}", exact=True).click()
        expect(page.get_by_test_id("ai-transcript")).to_contain_text("Nothing urgent.")
        assert not errors
    finally:
        admin.call("PUT", "/features/AI_ASSISTANT", {"enabled": False})


def test_page_explains_when_unavailable(page: Page, errors, client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "")
    sign_in(page)
    page.goto("/assistant")
    expect(page.get_by_text("The AI assistant is not set up on this server")).to_be_visible()
    assert not errors
