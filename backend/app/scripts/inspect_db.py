import sqlite3
import os

db_path = "skillsync.db"
if not os.path.exists(db_path):
    print("Database file does not exist.")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cur.fetchall()
    print("Found tables:")
    for (tbl_name,) in tables:
        cur.execute(f"PRAGMA table_info({tbl_name});")
        columns = [(c[1], c[2], bool(c[3]), c[4], bool(c[5])) for c in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {tbl_name};")
        count = cur.fetchone()[0]
        print(f"\n--- Table: {tbl_name} ({count} rows) ---")
        for col_name, col_type, not_null, default_val, is_pk in columns:
            print(f"  {col_name}: {col_type} (nullable={not not_null}, pk={is_pk}, default={default_val})")
        
        # Check indices
        cur.execute(f"PRAGMA index_list({tbl_name});")
        indices = cur.fetchall()
        if indices:
            print(f"  Indices: {indices}")
    conn.close()
