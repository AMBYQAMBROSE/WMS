from collections.abc import Callable, Coroutine
from typing import Any

from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from app.api.idempotency import record_response


class TransactionalRoute(APIRoute):
    """Commits the request's transaction after the endpoint ran but *before* the response is sent.

    FastAPI closes request-scoped dependencies (get_db, which commits) only after the response has gone out, so a
    commit that failed there (a deadlock, a constraint checked at commit) would follow a success response for data that
    was never saved. Committing here turns that into an error response instead. It is also where the response of an
    Idempotency-Key request is stored, in the same transaction as the change it reports (app/api/idempotency.py).

    Every router uses it: APIRouter(route_class=TransactionalRoute, ...).
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def commit_then_respond(request: Request) -> Response:
            response = await handler(request)
            db = getattr(request.state, "db", None)
            if db is not None:
                await run_in_threadpool(_finish, db, request, response)
            return response

        return commit_then_respond


def _finish(db, request: Request, response: Response) -> None:
    record_response(request, response)
    db.commit()
