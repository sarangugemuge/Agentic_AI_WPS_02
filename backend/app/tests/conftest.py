"""
pytest configuration and fixtures for SkillSync backend tests.
Uses in-memory SQLite for isolation.
"""
import asyncio
import pathlib
import sys
import pytest

backend_dir = pathlib.Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Create tables in test DB before tests, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    """Async HTTP test client for FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac
