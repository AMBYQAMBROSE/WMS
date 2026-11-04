from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Sync engine + pyodbc: FastAPI `def` (non-async) endpoints run in a thread pool automatically.
# Current concurrency does not justify an async driver (aioodbc); keep it simple and revisit if needed.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
)
# Small pool used only for document numbering: the business request already holds one connection; taking the second from the same pool
# lets every connection be held by requests waiting for a second one under load, deadlocking until timeout (seen in load tests)
numbering_engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
