import asyncio
import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, load_current_user, oauth2_scheme
from app.core.db import SessionLocal
from app.services.live_service import feed

router = APIRouter(prefix="/events", tags=["events"])

HEARTBEAT_SECONDS = 15
# Streams end after this long and the browser reconnects: tokens are re-checked, deactivated users drop off,
# and nothing pins a backend process forever
STREAM_SECONDS = 600


def _authenticate(token: str) -> CurrentUser:
    # Its own short session: a request-scoped one (get_db) would hold a pooled connection for the whole stream
    with SessionLocal() as db:
        return load_current_user(db, token)


@router.get("/stream")
async def stream_changes(token: str = Depends(oauth2_scheme)):
    """Server-sent events: batches of {type, id, parent_id, action, doc_type} as data is changed by anyone in the tenant.
    The browser refetches what it shows; the events carry no values. See app/services/live_service.py."""
    user = await asyncio.to_thread(_authenticate, token)
    queue = feed.subscribe(user.tenant_id)

    async def body():
        try:
            # retry: how long the browser waits before reconnecting after the stream ends
            yield 'retry: 3000\nevent: ready\ndata: {}\n\n'
            ends_at = time.monotonic() + STREAM_SECONDS
            while time.monotonic() < ends_at:
                try:
                    batch = [await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)]
                except TimeoutError:
                    yield ": ping\n\n"  # comment line: keeps proxies from closing an idle connection
                    continue
                while not queue.empty():
                    batch.append(queue.get_nowait())
                yield f"data: {json.dumps(batch)}\n\n"
        finally:
            feed.unsubscribe(user.tenant_id, queue)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        # X-Accel-Buffering: nginx passes events through immediately instead of buffering the response
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
