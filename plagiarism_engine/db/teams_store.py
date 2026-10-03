"""Teams and team membership."""

from typing import List, Dict, Any, Optional

from .helpers import clean_str


class TeamsStoreMixin:
    """Teams and team membership. Mixed into SystemDBStore."""

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------
    def create_team(self, team_id: str, name: str, college_id: Optional[str]) -> None:
        """Insert a new team."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            tid = clean_str(team_id)
            tname = clean_str(name)
            tcollege = clean_str(college_id)
            if self.mode == "postgresql":
                cur.execute("""
                    INSERT INTO teams (id, name, college_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                """, (tid, tname, tcollege))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO teams (id, name, college_id)
                    VALUES (?, ?, ?);
                """, (tid, tname, tcollege))
            conn.commit()
        finally:
            conn.close()

    def get_all_teams(self, college_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all teams, optionally filtered by college_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if college_id:
                cid = clean_str(college_id)
                if self.mode == "postgresql":
                    cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE college_id = %s ORDER BY created_at DESC;", (cid,))
                else:
                    cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE college_id = ? ORDER BY created_at DESC;", (cid,))
            else:
                cur.execute("SELECT id, name, college_id, created_at FROM teams ORDER BY created_at DESC;")
            rows = cur.fetchall()

            teams = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    teams.append(dict(r))
                else:
                    teams.append({"id": r[0], "name": r[1], "college_id": r[2], "created_at": r[3]})
            return teams
        finally:
            conn.close()

    def get_team_by_id(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single team by id, or None if not found."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            tid = clean_str(team_id)
            if self.mode == "postgresql":
                cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE id = %s;", (tid,))
            else:
                cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE id = ?;", (tid,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {"id": row[0], "name": row[1], "college_id": row[2], "created_at": row[3]}
        finally:
            conn.close()

    def update_team(self, team_id: str, **fields) -> None:
        """Update a subset of fields on a team record."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {"name", "college_id"}
            updates = {k: clean_str(v) for k, v in fields.items() if k in allowed and v is not None}
            if not updates:
                return
            if self.mode == "postgresql":
                set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(team_id)]
                cur.execute(f"UPDATE teams SET {set_clause} WHERE id = %s;", params)
            else:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(team_id)]
                cur.execute(f"UPDATE teams SET {set_clause} WHERE id = ?;", params)
            conn.commit()
        finally:
            conn.close()

    def delete_team(self, team_id: str) -> None:
        """Delete a team by id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            tid = clean_str(team_id)
            if self.mode == "postgresql":
                cur.execute("DELETE FROM teams WHERE id = %s;", (tid,))
            else:
                cur.execute("DELETE FROM teams WHERE id = ?;", (tid,))
            conn.commit()
        finally:
            conn.close()

    def add_team_member(self, team_id: str, student_id: str) -> None:
        """Link a student to a team by updating students.team_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            tid = clean_str(team_id)
            sid = clean_str(student_id)
            if self.mode == "postgresql":
                cur.execute("UPDATE students SET team_id = %s WHERE id = %s;", (tid, sid))
            else:
                cur.execute("UPDATE students SET team_id = ? WHERE id = ?;", (tid, sid))
            conn.commit()
        finally:
            conn.close()

    def remove_team_member(self, student_id: str) -> None:
        """Unlink a student from any team by clearing students.team_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            sid = clean_str(student_id)
            if self.mode == "postgresql":
                cur.execute("UPDATE students SET team_id = NULL WHERE id = %s;", (sid,))
            else:
                cur.execute("UPDATE students SET team_id = NULL WHERE id = ?;", (sid,))
            conn.commit()
        finally:
            conn.close()

    def get_team_members(self, team_id: str) -> List[Dict[str, Any]]:
        """Fetch all students assigned to a given team."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            tid = clean_str(team_id)
            if self.mode == "postgresql":
                cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE team_id = %s ORDER BY created_at DESC;", (tid,))
            else:
                cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE team_id = ? ORDER BY created_at DESC;", (tid,))
            rows = cur.fetchall()

            members = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    members.append(dict(r))
                else:
                    members.append({
                        "id": r[0], "enrollment_number": r[1], "name": r[2],
                        "college_id": r[3], "team_id": r[4], "created_at": r[5],
                    })
            return members
        finally:
            conn.close()
