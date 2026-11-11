"""AI assistant conversations (app/services/assistant).

Every message is kept exactly as exchanged with the model, as JSON content blocks: the user's questions, the
assistant's answers, and every tool call with its input and the data it returned. That is both what a follow-up
question replays to the model (thinking blocks must go back unchanged) and the record of what the assistant saw and
said on whose behalf. Not in the audit log: these rows are never edited, and their content is far too large for it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Unicode, UnicodeText, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class AssistantConversation(Base, TenantScopedMixin):
    __tablename__ = "assistant_conversation"
    __table_args__ = (Index("ix_assistant_conversation_user", "tenant_id", "user_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    # The first question, shortened: what the conversation list shows
    title: Mapped[str] = mapped_column(Unicode(200), nullable=False)


class AssistantMessage(Base):
    __tablename__ = "assistant_message"
    __table_args__ = (
        Index("ix_assistant_message_conversation", "conversation_id", "seq"),
        Index("ix_assistant_message_usage", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assistant_conversation.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # user: a question or tool results; assistant: a model response (text, thinking, tool calls)
    role: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    # JSON list of content blocks, as sent to or returned by the model
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Assistant responses only: which model answered, why it stopped, and what it cost
    model: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
