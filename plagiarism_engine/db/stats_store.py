"""Aggregate counts for the dashboard."""


from .helpers import row_get


class StatsStoreMixin:
    """Aggregate counts for the dashboard. Mixed into SystemDBStore."""

    # ------------------------------------------------------------------
    # Counts (dashboard)
    # ------------------------------------------------------------------
    def count_projects(self) -> int:
        """Return the total number of projects."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT COUNT(*) FROM projects;")
            else:
                cur.execute("SELECT COUNT(*) FROM projects;")
            row = cur.fetchone()
            if not row:
                return 0
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return int(row_get(row, 'count', row_get(row, 'COUNT(*)', 0)))
            return int(row[0])
        finally:
            conn.close()

    def count_teams(self) -> int:
        """Return the total number of teams."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT COUNT(*) FROM teams;")
            else:
                cur.execute("SELECT COUNT(*) FROM teams;")
            row = cur.fetchone()
            if not row:
                return 0
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return int(row_get(row, 'count', row_get(row, 'COUNT(*)', 0)))
            return int(row[0])
        finally:
            conn.close()

    def count_users(self) -> int:
        """Return the total number of users."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT COUNT(*) FROM users;")
            else:
                cur.execute("SELECT COUNT(*) FROM users;")
            row = cur.fetchone()
            if not row:
                return 0
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return int(row_get(row, 'count', row_get(row, 'COUNT(*)', 0)))
            return int(row[0])
        finally:
            conn.close()

    def count_files(self) -> int:
        """Return the total number of project files."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT COUNT(*) FROM project_files;")
            else:
                cur.execute("SELECT COUNT(*) FROM project_files;")
            row = cur.fetchone()
            if not row:
                return 0
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return int(row_get(row, 'count', row_get(row, 'COUNT(*)', 0)))
            return int(row[0])
        finally:
            conn.close()
