"""
Async SQLAlchemy database engine and session factory.
Uses DATABASE_URL from settings — defaults to local SQLite via aiosqlite.
Supports future migration to owner-controlled PostgreSQL seamlessly.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def get_normalized_database_url(raw_url: str) -> str:
    """Normalize DATABASE_URL for async drivers (aiosqlite / asyncpg)."""
    url = raw_url.strip()
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    if url.startswith("postgresql://") and "asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://")
    if url.startswith("postgres://") and "asyncpg" not in url:
        return url.replace("postgres://", "postgresql+asyncpg://")
    return url


DATABASE_URL = get_normalized_database_url(settings.database_url)

# Engine configuration
engine_kwargs = {"echo": settings.is_development}
if "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Cloud PostgreSQL optimizations (Render, Supabase, Neon)
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
async_session_factory = AsyncSessionLocal


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass


async def init_db() -> None:
    """Initialize database and execute non-destructive schema migrations."""
    from app.core.migrations import run_migrations
    await run_migrations(engine)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an active database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
