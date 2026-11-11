import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session, load_current_user, oauth2_scheme
from app.api.routing import TransactionalRoute
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.assistant import AssistantConversation, AssistantMessage
from app.services.assistant import agent

router = APIRouter(route_class=TransactionalRoute, prefix="/assistant", tags=["assistant"])


class AssistantStatus(BaseModel):
    available: bool
    # Why not, in words for the user
    reason: str | None
    model: str | None
    tokens_today: int
    # 0 = no daily limit
    daily_token_budget: int


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime


class ToolCall(BaseModel):
    label: str
    rows: int | None
    error: str | None


class Exchange(BaseModel):
    question: str
    answer: str
    tools: list[ToolCall]


class Transcript(BaseModel):
    id: uuid.UUID
    title: str
    exchanges: list[Exchange]


def _require_available(db: Session, user: CurrentUser) -> None:
    reason = agent.availability(db, user.tenant_id, user.permissions)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)


@router.get("/status", response_model=AssistantStatus)
def assistant_status(db: Session = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    """For every signed-in user: whether to show the assistant, and if not, why"""
    reason = agent.availability(db, user.tenant_id, user.permissions)
    return AssistantStatus(
        available=reason is None, reason=reason, model=agent.model_id() if settings.ai_provider else None,
        tokens_today=agent._tokens_today(user.tenant_id) if reason is None else 0,
        daily_token_budget=settings.ai_daily_token_budget,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    _require_available(db, user)
    return list(db.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.tenant_id == user.tenant_id, AssistantConversation.user_id == user.id,
               AssistantConversation.is_deleted == false())
        .order_by(AssistantConversation.updated_at.desc())
        .limit(50)
    ))


def _own(db: Session, user: CurrentUser, conversation_id: uuid.UUID) -> AssistantConversation:
    conversation = db.get(AssistantConversation, conversation_id)
    if conversation is None or conversation.user_id != user.id or conversation.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


def _question_text(blocks: list[dict]) -> str:
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    # The date preamble the agent adds for the model is not part of what the user asked
    return text.split("\n\n", 1)[1] if text.startswith("(Today is ") and "\n\n" in text else text


@router.get("/conversations/{conversation_id}", response_model=Transcript)
def get_conversation(
    conversation_id: uuid.UUID, db: Session = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)
):
    _require_available(db, user)
    conversation = _own(db, user, conversation_id)
    rows = db.scalars(
        select(AssistantMessage).where(AssistantMessage.conversation_id == conversation.id).order_by(AssistantMessage.seq)
    )
    exchanges: list[Exchange] = []
    pending: dict[str, ToolCall] = {}
    for row in rows:
        blocks = json.loads(row.content)
        if row.role == "user" and any(b.get("type") == "text" for b in blocks):
            exchanges.append(Exchange(question=_question_text(blocks), answer="", tools=[]))
            continue
        if not exchanges:
            continue
        current = exchanges[-1]
        for block in blocks:
            if block.get("type") == "text" and row.role == "assistant":
                current.answer += block.get("text", "")
            elif block.get("type") == "tool_use":
                call = ToolCall(label=agent._tool_label(block.get("name", ""), block.get("input")), rows=None, error=None)
                pending[block.get("id", "")] = call
                current.tools.append(call)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                call = pending.pop(block["tool_use_id"])
                if block.get("is_error"):
                    call.error = block.get("content") if isinstance(block.get("content"), str) else "Error"
                else:
                    call.rows = agent._rows_of(block.get("content", ""))
    return Transcript(id=conversation.id, title=conversation.title, exchanges=exchanges)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID, db: Session = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)
):
    _require_available(db, user)
    conversation = _own(db, user, conversation_id)
    conversation.is_deleted = True
    conversation.updated_by = user.id


def _authenticate(token: str) -> CurrentUser:
    # Its own short session: a request-scoped one would hold a pooled connection while the model answers
    with SessionLocal() as db:
        user = load_current_user(db, token)
        _require_available(db, user)
        return user


@router.post("/ask")
async def ask(data: AskIn, token: str = Depends(oauth2_scheme)):
    """Server-sent events, one JSON object each: conversation, text (answer as it is written), tool / tool_done
    (a lookup starting and finishing), done (with token usage) or error"""
    user = await asyncio.to_thread(_authenticate, token)

    async def body():
        async for event in agent.answer(user, data.question, data.conversation_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
