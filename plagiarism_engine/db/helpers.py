"""Shared DB helpers: driver detection, string sanitising, compression, row access."""

import zlib
import base64
from typing import Any

try:
    import psycopg2  # noqa: F401  (availability probe)
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DEFAULT_PG_URL = "postgresql://postgres:postgres@localhost:5432/plagiarism_engine_db"

def clean_str(val: Any) -> str:
    """Sanitizes string inputs to prevent NUL byte (0x00) PostgreSQL driver crashes."""
    if val is None:
        return ""
    s = str(val)
    return s.replace('\x00', '')

def compress_text(text: str) -> str:
    if not text:
        return ""
    try:
        return base64.b64encode(zlib.compress(text.encode('utf-8'))).decode('utf-8')
    except Exception:
        return text

def decompress_text(b64_text: str) -> str:
    if not b64_text:
        return ""
    try:
        return zlib.decompress(base64.b64decode(b64_text.encode('utf-8'))).decode('utf-8')
    except Exception:
        return b64_text

def _as_bool_flag(val: Any) -> int:
    """Normalize driver-specific boolean representations (bool/int/str) to 0/1."""
    if val is None:
        return 0
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return 1 if val else 0
    return 1 if clean_str(val).strip().lower() in {"1", "t", "true", "yes", "y"} else 0


def row_get(row: Any, key: str, default: Any = None) -> Any:
    """Dict-style .get() that also works for sqlite3.Row (it has keys() but no get())."""
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        keys = row.keys()
    except Exception:
        return default
    return row[key] if key in keys else default
