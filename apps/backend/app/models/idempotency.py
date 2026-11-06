"""Idempotency keys for API clients (app/api/idempotency.py).

A row is written in the same transaction as the request's business change, so it exists exactly when the change was
committed. The response is stored on it afterwards, for replaying to a client that retries with the same key.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Unicode, UnicodeText, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_key"

    # Keys are per user: two clients choosing the same key never see each other's responses
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    # Method, path, query and body: the same key with a different request is a client bug, refused
    request_hash: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # Null until the response is stored, right after the commit
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
