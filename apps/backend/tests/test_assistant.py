"""AI assistant: the tool loop, permissions, history, limits and error handling, with a scripted model in place of the
AI provider (tests never call a real model or spend money)."""

import copy
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.core.config import settings
from app.services.assistant import agent
from tests.conftest import login
from tests.helpers import Api, make_item, make_warehouse, put_away, receive


class Block(SimpleNamespace):
    def to_dict(self, mode="json"):
        return dict(vars(self))


def text(value: str) -> Block:
    return Block(type="text", text=value)


def tool(name: str, tool_input: dict, tool_id: str = "toolu_1") -> Block:
    return Block(type="tool_use", id=tool_id, name=name, input=tool_input)


def reply(*content: Block, stop_reason: str = "end_turn") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=1000, output_tokens=50, cache_read_input_tokens=800, cache_creation_input_tokens=0)
    return SimpleNamespace(content=list(content), stop_reason=stop_reason, model="claude-opus-5-5", usage=usage)


class FakeStream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        if isinstance(self.message, Exception):
            raise self.message
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for block in self.message.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)

    async def get_final_message(self):
        return self.message


class FakeModel:
    """Plays back scripted replies and records every request it was sent"""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.requests.append(copy.deepcopy(params))
        return FakeStream(self.replies.pop(0))


@pytest.fixture
def assistant_on(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    Api(client, admin_headers).call("PUT", "/features/AI_ASSISTANT", {"enabled": True})
    yield
    Api(client, admin_headers).call("PUT", "/features/AI_ASSISTANT", {"enabled": False})


def use_model(monkeypatch, *replies) -> FakeModel:
    model = FakeModel(*replies)
    monkeypatch.setattr(agent, "make_client", lambda: model)
    return model


def ask(client, headers, question: str, conversation_id: str | None = None) -> list[dict]:
    response = client.post("/api/v1/assistant/ask", headers=headers, json={"question": question, "conversation_id": conversation_id})
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def stocked(api: Api, unique: str, qty: float = 5) -> str:
    wh = make_warehouse(api, unique)
    item = make_item(api, wh, f"AI{unique}")
    receive(api, wh, item, qty)
    put_away(api, wh, item, qty)
    return f"AI{unique}"


def test_answers_by_looking_up_stock(client, admin_headers, unique, assistant_on, monkeypatch):
    sku = stocked(Api(client, admin_headers), unique)
    model = use_model(
        monkeypatch,
        reply(tool("stock_on_hand", {"sku": sku}), stop_reason="tool_use"),
        reply(text(f"You have **5** of {sku}.")),
    )
    events = ask(client, admin_headers, f"How many {sku} do we have?")

    assert [e["type"] for e in events] == ["conversation", "tool", "tool_done", "text", "done"]
    assert events[1]["label"] == f"stock_on_hand(sku={sku})"
    assert events[2]["rows"] == 1 and events[2]["error"] is None
    assert events[4]["usage"]["input_tokens"] == 2000

    # The tool result went back to the model with the real figures, in one user message
    result = model.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["is_error"] is False
    assert json.loads(result["content"])["total_on_hand"] == 5

    transcript = Api(client, admin_headers).get(f"/assistant/conversations/{events[0]['id']}")
    assert transcript["exchanges"] == [{
        "question": f"How many {sku} do we have?", "answer": f"You have **5** of {sku}.",
        "tools": [{"label": f"stock_on_hand(sku={sku})", "rows": 1, "error": None}],
    }]


def test_request_uses_caching_effort_and_fallbacks(client, admin_headers, assistant_on, monkeypatch):
    model = use_model(monkeypatch, reply(text("Hello")))
    ask(client, admin_headers, "Hi")
    params = model.requests[0]
    assert params["model"] == "claude-opus-5-5"
    assert params["cache_control"] == {"type": "ephemeral"}
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"] == {"effort": settings.ai_effort}
    assert params["fallbacks"] == "default" and params["betas"] == ["server-side-fallback-2026-07-01"]
    # The system prompt holds nothing that changes per request (it is cached); the date travels with the question
    assert "Today is" not in params["system"][0]["text"]
    assert params["messages"][0]["content"][0]["text"].startswith("(Today is ")
    assert all(t["eager_input_streaming"] for t in params["tools"])


def test_bedrock_gets_its_model_id_and_no_server_fallbacks(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "bedrock")
    params = agent.request_params([], [])
    assert params["model"] == "anthropic.claude-opus-5-5"
    assert "fallbacks" not in params and "betas" not in params


def test_tools_follow_the_users_permissions(client, admin_headers, unique, assistant_on, monkeypatch):
    admin = Api(client, admin_headers)
    sku = stocked(admin, unique)
    role = admin.post("/roles", {"code": f"AQ{unique}", "name": "Asks", "permission_codes": ["ai.assistant", "item.read"]})
    admin.post("/users", {"username": f"aq{unique}", "display_name": "Q", "password": "Asks@Test123", "role_codes": [role["code"]]})
    headers = login(client, f"aq{unique}", "Asks@Test123")

    model = use_model(
        monkeypatch,
        reply(tool("stock_on_hand", {"sku": sku}), stop_reason="tool_use"),  # tries a tool it was not offered
        reply(text("I cannot see stock levels with your account.")),
    )
    events = ask(client, headers, f"Stock of {sku}?")
    assert [t["name"] for t in model.requests[0]["tools"]] == ["find_items"]
    refused = model.requests[1]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "not allowed" in refused["content"]
    assert events[2]["error"] and "5" not in refused["content"]


def test_follow_up_replays_the_conversation_unchanged(client, admin_headers, assistant_on, monkeypatch):
    thinking = Block(type="thinking", thinking="", signature="sig-abc")
    model = use_model(monkeypatch, reply(thinking, text("First answer")), reply(text("Second answer")))
    first = ask(client, admin_headers, "First question")
    ask(client, admin_headers, "And a follow-up?", first[0]["id"])

    replayed = model.requests[1]["messages"]
    assert [m["role"] for m in replayed] == ["user", "assistant", "user"]
    # Thinking blocks must go back exactly as they came
    assert replayed[1]["content"] == [{"type": "thinking", "thinking": "", "signature": "sig-abc"},
                                      {"type": "text", "text": "First answer"}]
    assert replayed[2]["content"][0]["text"].endswith("And a follow-up?")


def test_invalid_tool_input_is_returned_to_the_model(client, admin_headers, assistant_on, monkeypatch):
    model = use_model(
        monkeypatch,
        reply(tool("stock_movements", {"sku": "X", "days": "lots"}), stop_reason="tool_use"),
        reply(text("Let me try again.")),
    )
    events = ask(client, admin_headers, "Movements?")
    result = model.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Invalid input" in result["content"]
    assert events[-1]["type"] == "done"


def test_refusal_runs_no_tools(client, admin_headers, assistant_on, monkeypatch):
    model = use_model(monkeypatch, reply(tool("dashboard", {}), stop_reason="refusal"))
    events = ask(client, admin_headers, "Something declined")
    assert events[-1] == {"type": "error", "message": "The AI declined to answer this question."}
    assert "tool" not in [e["type"] for e in events] and len(model.requests) == 1


def test_lookups_are_capped_per_question(client, admin_headers, assistant_on, monkeypatch):
    monkeypatch.setattr(settings, "ai_max_tool_rounds", 2)
    use_model(monkeypatch, *[reply(tool("dashboard", {}, f"toolu_{i}"), stop_reason="tool_use") for i in range(3)])
    events = ask(client, admin_headers, "Loop forever")
    assert sum(1 for e in events if e["type"] == "tool") == 2
    assert events[-1]["type"] == "error" and "more than 2 rounds" in events[-1]["message"]


def test_daily_budget_stops_further_questions(client, admin_headers, assistant_on, monkeypatch):
    use_model(monkeypatch, reply(text("One")))
    ask(client, admin_headers, "Spend some tokens")
    monkeypatch.setattr(settings, "ai_daily_token_budget", 1)
    model = use_model(monkeypatch, reply(text("Two")))
    events = ask(client, admin_headers, "And more")
    assert events == [{"type": "error", "message": "Today's AI usage limit for this company has been reached. It resets at midnight."}]
    assert model.requests == []


def test_provider_errors_read_as_plain_language(client, admin_headers, assistant_on, monkeypatch):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    busy = anthropic.RateLimitError("rate limited", response=httpx2.Response(429, request=request), body=None)
    use_model(monkeypatch, busy)
    events = ask(client, admin_headers, "Are you there?")
    assert events[-1] == {"type": "error", "message": agent.FRIENDLY_ERRORS["rate_limit"]}


def test_unavailable_until_set_up_switched_on_and_allowed(client, admin_headers, unique, monkeypatch):
    admin = Api(client, admin_headers)
    monkeypatch.setattr(settings, "ai_provider", "")
    assert "not set up" in admin.get("/assistant/status")["reason"]
    admin.call("POST", "/assistant/ask", {"question": "Hi"}, expect=403)

    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    admin.call("PUT", "/features/AI_ASSISTANT", {"enabled": False})
    assert "switched off" in admin.get("/assistant/status")["reason"]

    admin.call("PUT", "/features/AI_ASSISTANT", {"enabled": True})
    assert admin.get("/assistant/status")["available"] is True
    admin.post("/users", {"username": f"na{unique}", "display_name": "N", "password": "None@Test123"})
    nobody = Api(client, login(client, f"na{unique}", "None@Test123"))
    assert "not allowed" in nobody.get("/assistant/status")["reason"]
    nobody.call("POST", "/assistant/ask", {"question": "Hi"}, expect=403)
    admin.call("PUT", "/features/AI_ASSISTANT", {"enabled": False})


def test_conversations_are_private(client, admin_headers, unique, assistant_on, monkeypatch):
    use_model(monkeypatch, reply(text("Mine")))
    conversation = ask(client, admin_headers, "Private question")[0]["id"]
    admin = Api(client, admin_headers)
    admin.post("/users", {"username": f"ot{unique}", "display_name": "O", "password": "Other@Test123", "role_codes": ["ADMIN"]})
    other = Api(client, login(client, f"ot{unique}", "Other@Test123"))
    other.call("GET", f"/assistant/conversations/{conversation}", expect=404)
    assert conversation not in {c["id"] for c in other.get("/assistant/conversations")}
