"""System settings key/value store."""

import json
from typing import Dict, Any

from .helpers import clean_str


class SettingsStoreMixin:
    """System settings key/value store. Mixed into SystemDBStore."""

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _init_default_settings(self, cur) -> None:
        """Seed default settings if they do not already exist."""
        defaults = {
            "similarity_threshold": 65,
            "max_upload_size_mb": 500,
            "default_language": "en",
        }
        for key, value in defaults.items():
            k = clean_str(key)
            v = json.dumps(value)
            if self.mode == "postgresql":
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING;",
                    (k, v),
                )
            else:
                cur.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);",
                    (k, v),
                )

    def get_all_settings(self) -> Dict[str, Any]:
        """Return all settings as a JSON object (values are parsed from JSON)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT key, value FROM settings;")
            else:
                cur.execute("SELECT key, value FROM settings;")
            rows = cur.fetchall()

            settings = {}
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    key, value = r['key'], r['value']
                else:
                    key, value = r[0], r[1]
                try:
                    settings[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    settings[key] = value
            return settings
        finally:
            conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Return a single setting parsed from JSON, or default if missing."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            k = clean_str(key)
            if self.mode == "postgresql":
                cur.execute("SELECT value FROM settings WHERE key = %s LIMIT 1;", (k,))
            else:
                cur.execute("SELECT value FROM settings WHERE key = ? LIMIT 1;", (k,))
            row = cur.fetchone()
            if not row:
                return default
            val = row['value'] if (isinstance(row, dict) or hasattr(row, 'keys')) else row[0]
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        finally:
            conn.close()

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Bulk update settings. Values are JSON-encoded before storage."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            for key, value in settings.items():
                k = clean_str(key)
                v = json.dumps(value)
                if self.mode == "postgresql":
                    cur.execute(
                        "INSERT INTO settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                        (k, v),
                    )
                else:
                    cur.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);",
                        (k, v),
                    )
            conn.commit()
        finally:
            conn.close()
