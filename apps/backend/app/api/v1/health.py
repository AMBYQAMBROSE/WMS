from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routing import TransactionalRoute
from app.core.config import settings
from app.core.db import engine

router = APIRouter(route_class=TransactionalRoute, tags=["health"])

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _code_revision() -> str | None:
    config = Config(str(_BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


CODE_REVISION = _code_revision()


@router.get("/health")
def health_check() -> dict:
    """Liveness check: returns as long as the process is up, without touching the database (used by the container health check)"""
    return {"status": "ok", "version": settings.app_version}


@router.get("/health/ready")
def readiness_check():
    """Readiness check: the database is reachable and its schema revision matches the code (the upgrade script uses this to tell whether migration finished)"""
    body = {"version": settings.app_version, "code_revision": CODE_REVISION}
    try:
        with engine.connect() as conn:
            body["db_revision"] = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001 - the readiness check only reports the reason, it does not raise
        return JSONResponse(status_code=503, content={**body, "status": "db_unavailable", "detail": str(exc)[:300]})
    if body["db_revision"] != CODE_REVISION:
        return JSONResponse(status_code=503, content={**body, "status": "migration_pending"})
    return {**body, "status": "ready"}
