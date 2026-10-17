"""
SkillSync SQLite to PostgreSQL Data Migration Script
Transfers all existing data from local skillsync.db into target PostgreSQL.
Preserves primary keys, foreign keys, timestamps, and resets PostgreSQL serial sequences.
"""
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add backend directory to sys.path so app imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.database import get_normalized_database_url, Base
from app.core.migrations import run_migrations


TABLE_ORDER = [
    "users",
    "repositories",
    "commit_history",
    "job_profiles",
    "job_skill_requirements",
    "assessments",
    "skill_findings",
    "evidence_citations",
    "skill_gaps",
    "webhook_deliveries",
]


async def migrate_data():
    sqlite_path = os.path.join(backend_dir, "skillsync.db")
    if not os.path.exists(sqlite_path):
        print(f"[-] SQLite database file not found at {sqlite_path}. Nothing to migrate.")
        return

    target_url = get_normalized_database_url(settings.database_url)
    if "sqlite" in target_url:
        print("[-] Target DATABASE_URL is still configured for SQLite!")
        print("    Please set DATABASE_URL=postgresql+asyncpg://... in backend/.env before running this script.")
        return

    print("=" * 65)
    print("SkillSync — SQLite to PostgreSQL Data Migration")
    print("=" * 65)
    print(f"Source (SQLite):     {sqlite_path}")
    masked_target = target_url.split("@")[-1] if "@" in target_url else target_url[:30] + "..."
    print(f"Destination (PG):    ...@{masked_target}")
    print("-" * 65)

    # 1. Open SQLite Source
    src_conn = sqlite3.connect(sqlite_path)
    src_conn.row_factory = sqlite3.Row
    src_cur = src_conn.cursor()

    # 2. Connect to PostgreSQL and run migrations to ensure tables exist
    print("[1/3] Connecting to PostgreSQL and verifying table schemas...")
    pg_engine = create_async_engine(target_url, echo=False)
    await run_migrations(pg_engine)

    # 3. Transfer records table by table
    print("\n[2/3] Transferring records across tables...")
    total_migrated = 0

    async with pg_engine.begin() as pg_conn:
        for table_name in TABLE_ORDER:
            # Check if source table exists
            src_cur.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';"
            )
            if not src_cur.fetchone():
                continue

            # Fetch all rows from SQLite
            src_cur.execute(f"SELECT * FROM {table_name};")
            rows = src_cur.fetchall()
            if not rows:
                print(f"  - {table_name:<24}: 0 rows (skipped)")
                continue

            from sqlalchemy.dialects.postgresql import insert as pg_insert

            sa_table = Base.metadata.tables.get(table_name)
            if sa_table is None:
                continue

            insert_stmt = pg_insert(sa_table).on_conflict_do_nothing()

            # Convert sqlite3.Row objects to dicts with datetime parsing
            data = []
            for row in rows:
                d = dict(row)
                for k, v in d.items():
                    if v is not None and isinstance(v, str):
                        if "_at" in k:
                            try:
                                dt = datetime.fromisoformat(v)
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                d[k] = dt
                            except Exception:
                                pass
                        elif k in ("status", "trigger_event") and table_name in ("assessments", "skill_findings"):
                            d[k] = v.upper()
                data.append(d)

            await pg_conn.execute(insert_stmt, data)

            count = len(data)
            total_migrated += count
            print(f"  + {table_name:<24}: {count} rows migrated successfully")

        # 4. Synchronize PostgreSQL identity / serial sequences
        print("\n[3/3] Synchronizing PostgreSQL sequence values...")
        for table_name in TABLE_ORDER:
            try:
                seq_sql = text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table_name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                        true
                    );
                """)
                await pg_conn.execute(seq_sql)
            except Exception:
                # Table might not have an identity sequence or is empty
                pass

    src_conn.close()
    await pg_engine.dispose()

    print("=" * 65)
    print(f"[SUCCESS] Migration completed! Total {total_migrated} records copied to PostgreSQL.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(migrate_data())
