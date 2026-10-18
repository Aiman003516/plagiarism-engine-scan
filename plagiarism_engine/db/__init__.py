"""
Relational storage package for the Plagiarism Detection Engine.

`SystemDBStore` is assembled from per-domain mixins so each concern lives in its
own small module while callers keep using one object:

    from plagiarism_engine.db import SystemDBStore
"""

from .helpers import (
    HAS_PSYCOPG2,
    DEFAULT_PG_URL,
    clean_str,
    compress_text,
    decompress_text,
    _as_bool_flag,
    row_get,
)
from .connection import ConnectionMixin
from .schema import SchemaMixin
from .projects_store import ProjectsStoreMixin
from .users_store import UsersStoreMixin
from .teams_store import TeamsStoreMixin
from .fingerprint_store import FingerprintStoreMixin
from .stats_store import StatsStoreMixin
from .settings_store import SettingsStoreMixin


class SystemDBStore(
    ConnectionMixin,
    SchemaMixin,
    ProjectsStoreMixin,
    UsersStoreMixin,
    TeamsStoreMixin,
    FingerprintStoreMixin,
    StatsStoreMixin,
    SettingsStoreMixin,
):
    """
    Production PostgreSQL Relational Storage Manager.
    Automatically creates the 'plagiarism_engine_db' database on local PostgreSQL,
    persisting projects, research papers, keywords, files, and plagiarism scan reports.
    """


class _LazyDBStoreProxy:
    """Lazy proxy that resolves to app.state.get_db() or a default SystemDBStore singleton."""

    _fallback_instance = None

    def _resolve(self) -> SystemDBStore:
        try:
            from app import state as app_state
            if app_state._db is not None:
                return app_state._db
            return app_state.get_db()
        except Exception:
            if self._fallback_instance is None:
                self._fallback_instance = SystemDBStore()
            return self._fallback_instance

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


store = _LazyDBStoreProxy()


__all__ = [
    "SystemDBStore",
    "store",
    "HAS_PSYCOPG2",
    "DEFAULT_PG_URL",
    "clean_str",
    "compress_text",
    "decompress_text",
    "_as_bool_flag",
    "row_get",
]

