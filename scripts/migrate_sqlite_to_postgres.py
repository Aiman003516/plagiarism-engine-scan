import os
import sqlite3
import psycopg2
from pathlib import Path
import json
from datetime import datetime

SQLITE_DB = os.path.join("data", "system_db.sqlite")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "dbname=plagiarism user=postgres password=postgres host=localhost port=5432")

def migrate():
    print(f"Connecting to SQLite: {SQLITE_DB}")
    if not os.path.exists(SQLITE_DB):
        print("SQLite DB not found, nothing to migrate.")
        return

    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_cur = sqlite_conn.cursor()

    print(f"Connecting to PostgreSQL: {POSTGRES_DSN}")
    pg_conn = psycopg2.connect(POSTGRES_DSN)
    pg_cur = pg_conn.cursor()

    # Disable constraints for fast load
    pg_cur.execute("SET session_replication_role = 'replica';")

    tables = ["teams", "users", "settings", "projects", "project_files", "scan_reports", "fingerprint_index"]

    for table in tables:
        # Check if table exists in sqlite
        sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not sqlite_cur.fetchone():
            continue
            
        sqlite_cur.execute(f"SELECT * FROM {table}")
        rows = sqlite_cur.fetchall()
        if not rows:
            print(f"Table {table} is empty. Skipping.")
            continue

        print(f"Migrating {len(rows)} rows for table {table}...")
        
        # Get column names
        sqlite_cur.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in sqlite_cur.fetchall()]
        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        insert_query = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
        
        # executemany in psycopg2
        import psycopg2.extras
        psycopg2.extras.execute_batch(pg_cur, insert_query, rows)

    # Re-enable constraints
    pg_cur.execute("SET session_replication_role = 'origin';")
    pg_conn.commit()
    
    # Update sequences for SERIAL columns
    try:
        pg_cur.execute("SELECT setval('fingerprint_index_id_seq', COALESCE((SELECT MAX(id)+1 FROM fingerprint_index), 1), false);")
        pg_conn.commit()
    except Exception as e:
        print(f"Failed to update sequence: {e}")
        pg_conn.rollback()

    print("Migration complete!")

    sqlite_conn.close()
    pg_cur.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
