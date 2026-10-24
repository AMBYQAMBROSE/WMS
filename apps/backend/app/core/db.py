from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# 同步引擎 + pyodbc：FastAPI 的 `def`（非 async）端点会自动跑在线程池里，
# 现阶段并发量不需要上 aioodbc 异步驱动，保持简单。后续如有高并发需求再评估切换。
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
