from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .config import get_settings, Settings
from .tracing import instrument_sqlalchemy

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session
except Exception:  # pragma: no cover - SQLAlchemy optional at scaffold time
    create_engine = None  # type: ignore
    sessionmaker = None  # type: ignore
    Session = object  # type: ignore


_engine = None
_SessionLocal = None


def init_engine(database_url: str | None = None, settings: Settings | None = None) -> None:
    global _engine, _SessionLocal
    settings = settings or get_settings()
    database_url = database_url or settings.DATABASE_URL
    if not database_url or create_engine is None or sessionmaker is None:
        return
    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        echo=settings.DB_ECHO,
    )
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    instrument_sqlalchemy(_engine)


@contextmanager
def get_session() -> Iterator["Session"]:
    if _SessionLocal is None:  # lazy init
        init_engine()
    if _SessionLocal is None:  # still None -> yield a dummy context
        yield None  # type: ignore
        return
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:  # pragma: no cover
        db.rollback()
        raise
    finally:
        db.close()
