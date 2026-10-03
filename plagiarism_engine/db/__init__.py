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


__all__ = [
    "SystemDBStore",
    "HAS_PSYCOPG2",
    "DEFAULT_PG_URL",
    "clean_str",
    "compress_text",
    "decompress_text",
    "_as_bool_flag",
    "row_get",
]
