"""Test fixtures: integration tests against a real SQL Server database.

Tests never touch the development database: the database name from DATABASE_URL gets a "_test" suffix
(override with TEST_DATABASE_URL). The test database is created if missing, migrated to head and seeded
once per run. Tests do not clean up after themselves; every test creates its own master data with unique
codes, so runs never interfere with each other and the database can be reused across runs.
"""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
ADMIN_PASSWORD = "Admin@Test123"

# Must happen before app.core.db is imported anywhere: the engine is created from settings at import time
_dev_url = make_url(settings.database_url)
_test_url = make_url(
    os.environ.get("TEST_DATABASE_URL") or _dev_url.set(database=f"{_dev_url.database}_test")
)
if _test_url.database == _dev_url.database and not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("Refusing to run tests against the development database")
settings.database_url = _test_url.render_as_string(hide_password=False)
settings.jwt_secret_key = "test-only-secret-key-that-is-long-enough"


def _create_database() -> None:
    master = create_engine(
        _test_url.set(database="master").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with master.connect() as conn:
        conn.execute(
            text(f"IF DB_ID(N'{_test_url.database}') IS NULL CREATE DATABASE [{_test_url.database}]")
        )
    master.dispose()


def _migrate_and_seed() -> None:
    from alembic import command
    from alembic.config import Config

    from scripts.seed import apply, load_preset

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    apply(load_preset("standard"), ADMIN_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    _create_database()
    _migrate_and_seed()


@pytest.fixture(scope="session")
def client(database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client) -> dict[str, str]:
    return login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture
def unique() -> str:
    """Short unique suffix for codes, so tests can share one database"""
    return uuid.uuid4().hex[:8].upper()
