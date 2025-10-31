import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import Column, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from .settings import DATABASE_URL


def _ensure_async_driver(url: str) -> str:
    if not url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    s = scheme.lower()
    if s.startswith("sqlite") and "aiosqlite" not in s:
        return "sqlite+aiosqlite://" + rest
    if (s in ("postgres", "postgresql") or s.startswith("postgresql+")) and "asyncpg" not in s:
        return "postgresql+asyncpg://" + rest
    return url


DATABASE_URL = _ensure_async_driver(DATABASE_URL)

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class Molecule(Base):
    __tablename__ = "molecules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    smiles = Column(String(4096), nullable=False, unique=True)


async def _wait_for_db(max_attempts: int = 30, delay_seconds: float = 1.0):
    for _ in range(max_attempts):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                return
        except Exception:
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("Database is not reachable after waiting")


async def init_db():
    await _wait_for_db()


@asynccontextmanager
async def db_session_scope():
    session: AsyncSession = SessionLocal()
    try:
        async with session.begin():
            yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db():
    async with db_session_scope() as session:
        yield session


# for testing purposes
async def _create_all_async():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _drop_all_async():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def create_all_sync():
    asyncio.run(_create_all_async())


def drop_all_sync():
    try:
        asyncio.run(_drop_all_async())
    except Exception:
        pass
