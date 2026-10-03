"""Connection management: constructor, PostgreSQL bootstrap, SQLite fallback."""

import os
import sqlite3
from typing import Optional
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    pass

from .helpers import HAS_PSYCOPG2, DEFAULT_PG_URL


class ConnectionMixin:
    """Connection management: constructor, PostgreSQL bootstrap, SQLite fallback. Mixed into SystemDBStore."""

    def __init__(self, pg_connection_string: Optional[str] = None, sqlite_db_path: str = "./system_db.sqlite"):
        self.pg_conn_str = pg_connection_string or os.getenv("DATABASE_URL") or DEFAULT_PG_URL
        self.sqlite_path = sqlite_db_path
        self.mode = "sqlite"
        self.pool = None

        if HAS_PSYCOPG2:
            try:
                self._ensure_pg_database_exists()
                from psycopg2.pool import ThreadedConnectionPool
                self.pool = ThreadedConnectionPool(2, 10, self.pg_conn_str)
                self.mode = "postgresql"
            except Exception as e:
                print(f"Failed to initialize PostgreSQL pool: {e}")
                self.mode = "sqlite"

        self._init_schema()

    def _ensure_pg_database_exists(self):
        """Connect to default 'postgres' database and create 'plagiarism_engine_db' if it doesn't exist."""
        try:
            base_conn_str = "postgresql://postgres:postgres@localhost:5432/postgres"
            conn = psycopg2.connect(base_conn_str)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            
            cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'plagiarism_engine_db';")
            exists = cur.fetchone()
            if not exists:
                cur.execute("CREATE DATABASE plagiarism_engine_db;")
            cur.close()
            conn.close()
        except Exception:
            pass

    def _get_connection(self):
        if self.mode == "postgresql":
            conn = self.pool.getconn()
            # We override close so it puts the connection back to the pool instead of closing it
            # since all methods currently do conn.close()
            original_close = conn.close
            def close_override():
                self.pool.putconn(conn)
            conn.close = close_override
            return conn
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            return conn
