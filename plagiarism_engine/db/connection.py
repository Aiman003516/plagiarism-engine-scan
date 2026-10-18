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

_DEFAULT_URL_WARNED = False


def _warn_default_url_once() -> None:
    """Print a single warning per process when DATABASE_URL is unset and the dev default is used."""
    global _DEFAULT_URL_WARNED
    if not _DEFAULT_URL_WARNED:
        _DEFAULT_URL_WARNED = True
        print("[DB] WARNING: DATABASE_URL is not set; using the built-in local development default. "
              "Set DATABASE_URL in .env for any shared or production deployment.")


class _PooledPGConnection:
    """Proxy around a psycopg2 connection that safely returns it to the pool on close()."""

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                if getattr(self._conn, "closed", 0) == 0:
                    # Roll back any open read transaction or aborted transaction before pool return
                    info = getattr(self._conn, "info", None)
                    if info is not None and getattr(info, "transaction_status", 0) != 0:
                        self._conn.rollback()
            except Exception:
                pass
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


class ConnectionMixin:
    """Connection management: constructor, PostgreSQL bootstrap, SQLite fallback. Mixed into SystemDBStore."""

    def __init__(self, pg_connection_string: Optional[str] = None, sqlite_db_path: str = "./system_db.sqlite"):
        env_url = os.getenv("DATABASE_URL")
        self.pg_conn_str = pg_connection_string or env_url or DEFAULT_PG_URL
        if not pg_connection_string and not env_url:
            _warn_default_url_once()
        self.sqlite_path = sqlite_db_path
        self.mode = "sqlite"
        self.pool = None
        self.has_pgvector = False

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
        """Create the configured target database if it does not exist yet.

        The admin connection reuses the user / password / host / port of the configured DSN
        and only swaps the database name for the always-present 'postgres' maintenance DB.
        """
        try:
            from psycopg2.extensions import parse_dsn
            from psycopg2 import sql

            params = parse_dsn(self.pg_conn_str)
            target_db = params.get("dbname")
            if not target_db or target_db == "postgres":
                return
            admin_params = {k: v for k, v in params.items() if k != "dbname"}
            admin_params["dbname"] = "postgres"

            conn = psycopg2.connect(**admin_params)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;", (target_db,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(target_db)))
            cur.close()
            conn.close()
        except Exception:
            pass

    def _get_connection(self):
        if self.mode == "postgresql":
            conn = self.pool.getconn()
            return _PooledPGConnection(conn, self.pool)
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            return conn

