from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def to_async_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_engine(url: str) -> AsyncEngine:
    async_url = to_async_url(url)
    connect_args: dict = {}
    if async_url.startswith("postgresql+psycopg"):
        connect_args["prepare_threshold"] = None  # works behind Supabase/pgbouncer transaction pooling
    return create_async_engine(async_url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    from app.db import models  # noqa: F401 - registers tables

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
