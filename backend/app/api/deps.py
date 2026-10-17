"""Shared FastAPI dependencies."""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db  # re-export for convenient import

__all__ = ["get_db"]
