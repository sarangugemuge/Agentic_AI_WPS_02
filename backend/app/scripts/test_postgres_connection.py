"""
Quick PostgreSQL Connection Verification Script.
Tests connectivity, verifies PostgreSQL version, and reports status WITHOUT exposing secrets.
"""
import asyncio
import os
import sys
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.database import get_normalized_database_url


async def test_connection():
    target_url = get_normalized_database_url(settings.database_url)
    print("=" * 60)
    print("SkillSync — PostgreSQL Connection Test")
    print("=" * 60)

    if "sqlite" in target_url:
        print("[!] Current DATABASE_URL is still pointing to SQLite:")
        print(f"    {target_url}")
        print("\nTo test your Render database, paste your Render URL into backend/.env")
        return

    # Mask host and credentials for safety
    masked_target = target_url.split("@")[-1] if "@" in target_url else "..."
    print(f"Target Host/Database: ...@{masked_target}")
    print("Attempting asynchronous connection via asyncpg...")

    t0 = time.time()
    try:
        engine = create_async_engine(target_url, echo=False)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version();"))
            pg_version = res.scalar()
            elapsed_ms = (time.time() - t0) * 1000

            print("\n[+] SUCCESS! Connected to PostgreSQL.")
            print(f"    Latency: {elapsed_ms:.1f}ms")
            print(f"    Server:  {pg_version.split(',')[0] if pg_version else 'PostgreSQL'}")

        await engine.dispose()
        print("=" * 60)
    except Exception as e:
        print(f"\n[-] FAILED to connect: {type(e).__name__}")
        print(f"    Details: {e}")
        print("\nTroubleshooting tips:")
        print("1. Ensure '?ssl=require' is included at the end of the URL.")
        print("2. Check that you used the 'External Database URL' from Render.")
        print("3. Check for special characters in your password (they must be URL-encoded).")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_connection())
