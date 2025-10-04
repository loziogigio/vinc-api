from __future__ import annotations

from typing import Optional

from .config import get_settings, Settings

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
except Exception:  # pragma: no cover - optional dependency at scaffold time
    AsyncIOMotorClient = None  # type: ignore
    AsyncIOMotorDatabase = None  # type: ignore

_mongo_client: Optional["AsyncIOMotorClient"] = None
_mongo_db: Optional["AsyncIOMotorDatabase"] = None


def init_mongo(url: str | None = None, settings: Settings | None = None) -> None:
    global _mongo_client, _mongo_db
    if AsyncIOMotorClient is None:
        return
    settings = settings or get_settings()
    url = url or settings.MONGO_URL
    if not url:
        return
    _mongo_client = AsyncIOMotorClient(
        url,
        minPoolSize=settings.MONGO_MIN_POOL_SIZE,
        maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
        uuidRepresentation="standard",
    )
    _mongo_db = _mongo_client.get_database(settings.MONGO_DB)


def get_mongo_client() -> Optional["AsyncIOMotorClient"]:
    return _mongo_client


def get_mongo_db() -> Optional["AsyncIOMotorDatabase"]:
    return _mongo_db


def close_mongo() -> None:
    global _mongo_client, _mongo_db
    if _mongo_client is not None:  # pragma: no cover - runtime cleanup
        _mongo_client.close()
    _mongo_client = None
    _mongo_db = None

