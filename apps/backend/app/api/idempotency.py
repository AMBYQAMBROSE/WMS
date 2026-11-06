"""Idempotency-Key for API clients: a POST retried with the same key is not executed twice.

Integration clients (ERP pushing orders, scripts) retry on timeouts; without this, a request that reached the server but
whose response was lost would create a second order. Opt-in per request: send `Idempotency-Key: <unique string>`.
The PDA does the same for its documents with `client_request_id` in the body.

How it works, all inside the request's own database transaction:
1. `idempotency_guard` (a router dependency) claims the key under a key-range lock, so a duplicate arriving while the
   original runs waits for it.
2. TransactionalRoute (app/api/routing.py) stores the response on the key via `record_response`, then commits: the key,
   its response and the business change commit together or not at all.
3. A retry finds the key and gets the stored response back, marked `Idempotent-Replayed: true`, without running again.
A failed request rolls back its key with everything else, so it can simply be retried.
"""

import hashlib
import json
from datetime import timedelta

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import load_current_user
from app.core.db import get_db
from app.core.errors import ConflictError, DomainError
from app.models.idempotency import IdempotencyKey
from app.services.document_common import utcnow

HEADER = "idempotency-key"
MAX_KEY_LENGTH = 100
# Larger responses are not kept: the key still prevents a second execution, and a retry gets 409
MAX_STORED_BYTES = 256 * 1024
RETENTION = timedelta(hours=24)


class IdempotentReplay(Exception):
    """Raised by the guard to answer with the stored response instead of running the endpoint"""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body


def replay_response(_: Request, exc: IdempotentReplay) -> Response:
    return Response(
        content=exc.body, status_code=exc.status_code, media_type="application/json",
        headers={"Idempotent-Replayed": "true"},
    )


async def idempotency_guard(request: Request, db: Session = Depends(get_db)) -> None:
    key = request.headers.get(HEADER)
    if request.method != "POST" or not key:
        return
    if len(key) > MAX_KEY_LENGTH:
        raise DomainError(f"Idempotency-Key is longer than {MAX_KEY_LENGTH} characters")
    body = await request.body()
    digest = hashlib.sha256(
        b"\n".join([request.method.encode(), request.url.path.encode(), request.url.query.encode(), body])
    ).hexdigest()
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    request.state.idempotency_claim = await run_in_threadpool(_claim, db, token, key, digest)


def _claim(db: Session, token: str, key: str, digest: str) -> IdempotencyKey:
    user = load_current_user(db, token)  # 401 for a missing or bad token, as the endpoint itself would answer
    # UPDLOCK + HOLDLOCK locks the key's range even when the row does not exist yet: a concurrent duplicate waits here
    # until this request commits (then finds the row with its response) or rolls back (then claims the key itself)
    row = db.scalars(
        select(IdempotencyKey)
        .where(IdempotencyKey.user_id == user.id, IdempotencyKey.key == key)
        .with_hint(IdempotencyKey, "WITH (UPDLOCK, HOLDLOCK)", "mssql")
    ).first()
    if row is None:
        row = IdempotencyKey(user_id=user.id, key=key, request_hash=digest, created_at=utcnow())
        db.add(row)
        db.flush()
        return row
    if row.request_hash != digest:
        raise DomainError("This Idempotency-Key was already used for a different request; use a new key for a new request")
    if row.status_code is None:
        raise ConflictError(
            "This request was already processed, but its response could not be kept. Look the result up instead of retrying."
        )
    raise IdempotentReplay(row.status_code, row.response_body or "")


def record_response(request: Request, response: Response) -> None:
    """Called by TransactionalRoute just before the commit, so the response commits with the change it reports"""
    claim: IdempotencyKey | None = getattr(request.state, "idempotency_claim", None)
    body = getattr(response, "body", None)  # streaming responses have none: not replayable
    if claim is None or body is None or not 200 <= response.status_code < 300 or len(body) > MAX_STORED_BYTES:
        return
    text = body.decode("utf-8", errors="replace")
    try:
        json.loads(text or "null")
    except ValueError:
        return  # only JSON responses are replayed; a retry of anything else gets 409, never a second run
    claim.status_code, claim.response_body = response.status_code, text


def purge(db: Session) -> int:
    """Called by the worker: keys only need to outlive client retries"""
    return db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < utcnow() - RETENTION)).rowcount
