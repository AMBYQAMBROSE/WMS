"""Who is making the current request, available anywhere without passing it down (audit log, structured logs).

The middleware puts a fresh RequestContext into a ContextVar for every request. FastAPI runs sync dependencies and
endpoints in worker threads with a *copy* of the context, so a value set there would never be seen by the others;
instead everyone shares the same mutable object and get_current_user fills in the user on it.
Outside a request (worker, scripts) the default is an empty context, recorded as the system.
"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    method: str | None = None
    path: str | None = None
    user_id: uuid.UUID | None = None
    username: str | None = None
    tenant_id: uuid.UUID | None = None


_current: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def current_context() -> RequestContext:
    context = _current.get()
    if context is None:
        context = RequestContext()
        _current.set(context)
    return context


def start_request(context: RequestContext):
    """Returns the token for end_request"""
    return _current.set(context)


def end_request(token) -> None:
    _current.reset(token)
