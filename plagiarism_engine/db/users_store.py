"""User accounts (JWT/RBAC) and student accounts."""

from typing import List, Dict, Any, Optional

from .helpers import clean_str, _as_bool_flag


class UsersStoreMixin:
    """User accounts (JWT/RBAC) and student accounts. Mixed into SystemDBStore."""

    # ------------------------------------------------------------------
    # Users (JWT auth / RBAC)
    # ------------------------------------------------------------------
    def create_user(self, id: str, name: str, email: str, password_hash: str, role: str, college_id: Optional[str]) -> None:
        """Insert a new user account."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            uid = clean_str(id)
            uname = clean_str(name)
            uemail = clean_str(email).lower()
            uph = clean_str(password_hash)
            urole = clean_str(role)
            ucollege = clean_str(college_id)

            if self.mode == "postgresql":
                cur.execute("""
                    INSERT INTO users (id, name, email, password_hash, role, college_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                """, (uid, uname, uemail, uph, urole, ucollege))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO users (id, name, email, password_hash, role, college_id)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (uid, uname, uemail, uph, urole, ucollege))
            conn.commit()
        finally:
            conn.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch a user by email, or None if not found."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            uemail = clean_str(email).lower()
            if self.mode == "postgresql":
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE email = %s;", (uemail,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE email = ?;", (uemail,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
                "role": row[4], "college_id": row[5], "created_at": row[6],
                "requires_password_change": row[7],
            }
        finally:
            conn.close()

    def get_user_or_student_by_login(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Unified authentication lookup for the RBAC pipeline.

        Resolution order:
          1. `users` table, matched by email (staff: ministry_admin / college_admin).
          2. `students` table, matched by enrollment_number (role='student').

        Student rows are mapped onto the same shape as a user record so the
        auth endpoints can treat both identities uniformly. Returns None when
        no account matches the identifier.
        """
        ident = clean_str(identifier).strip()
        if not ident:
            return None

        # 1) Staff / admin accounts keyed by email
        user = self.get_user_by_email(ident)
        if user:
            mapped = dict(user)
            mapped["requires_password_change"] = _as_bool_flag(mapped.get("requires_password_change"))
            mapped["is_student"] = False
            return mapped

        # 2) Student accounts keyed by enrollment_number
        student = self.get_student_credentials_by_enrollment_number(ident)
        if not student:
            return None

        return {
            "id": student.get("id"),
            "name": student.get("name"),
            # Students have no email; the enrollment number is their login identity.
            "email": student.get("enrollment_number"),
            "enrollment_number": student.get("enrollment_number"),
            "password_hash": student.get("password_hash"),
            "role": "student",
            "college_id": student.get("college_id"),
            "team_id": student.get("team_id"),
            "requires_password_change": _as_bool_flag(student.get("requires_password_change")),
            "is_student": True,
            "created_at": student.get("created_at"),
        }

    def get_user_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a user by id, or None if not found."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            uid = clean_str(id)
            if self.mode == "postgresql":
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE id = %s;", (uid,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE id = ?;", (uid,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
                "role": row[4], "college_id": row[5], "created_at": row[6],
                "requires_password_change": row[7],
            }
        finally:
            conn.close()

    def get_all_users(self, role_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all users, optionally filtered by role."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if role_filter:
                rrole = clean_str(role_filter)
                if self.mode == "postgresql":
                    cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE role = %s ORDER BY created_at DESC;", (rrole,))
                else:
                    cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users WHERE role = ? ORDER BY created_at DESC;", (rrole,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change FROM users ORDER BY created_at DESC;")
            rows = cur.fetchall()

            users = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    users.append(dict(r))
                else:
                    users.append({
                        "id": r[0], "name": r[1], "email": r[2], "password_hash": r[3],
                        "role": r[4], "college_id": r[5], "created_at": r[6],
                        "requires_password_change": r[7],
                    })
            return users
        finally:
            conn.close()

    def update_user(self, id: str, **fields) -> None:
        """Update a subset of fields on a user record."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {"name", "email", "password_hash", "role", "college_id", "requires_password_change"}
            updates = {}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    if key == "email":
                        updates[key] = clean_str(value).lower()
                    elif key == "requires_password_change":
                        updates[key] = _as_bool_flag(value)
                    else:
                        updates[key] = clean_str(value)
            if not updates:
                return

            if self.mode == "postgresql":
                set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(id)]
                cur.execute(f"UPDATE users SET {set_clause} WHERE id = %s;", params)
            else:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(id)]
                cur.execute(f"UPDATE users SET {set_clause} WHERE id = ?;", params)
            conn.commit()
        finally:
            conn.close()

    def delete_user(self, id: str) -> None:
        """Delete a user account by id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            uid = clean_str(id)
            if self.mode == "postgresql":
                cur.execute("DELETE FROM users WHERE id = %s;", (uid,))
            else:
                cur.execute("DELETE FROM users WHERE id = ?;", (uid,))
            conn.commit()
        finally:
            conn.close()

    def create_student(self, id: str, enrollment_number: str, name: str, password_hash: str,
                       requires_password_change: bool = True) -> None:
        """
        Insert a new student account keyed by enrollment_number.

        Students authenticate with their enrollment number instead of an email.
        `requires_password_change` defaults to TRUE so self-registered and
        admin-provisioned students are forced to rotate the initial password
        on their first login.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            sid = clean_str(id)
            senum = clean_str(enrollment_number).strip()
            sname = clean_str(name)
            sph = clean_str(password_hash)
            sflag = _as_bool_flag(requires_password_change)

            if self.mode == "postgresql":
                cur.execute("""
                    INSERT INTO students (id, enrollment_number, name, password_hash, requires_password_change)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                """, (sid, senum, sname, sph, sflag))
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO students (id, enrollment_number, name, password_hash, requires_password_change)
                    VALUES (?, ?, ?, ?, ?);
                """, (sid, senum, sname, sph, sflag))
            conn.commit()
        finally:
            conn.close()


    def get_student_by_enrollment_number(self, enrollment_number: str) -> Optional[Dict[str, Any]]:
        """Fetch a student by enrollment number (used for team member lookup)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            enum = clean_str(enrollment_number)
            if self.mode == "postgresql":
                cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE enrollment_number = %s;", (enum,))
            else:
                cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE enrollment_number = ?;", (enum,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "enrollment_number": row[1], "name": row[2],
                "college_id": row[3], "team_id": row[4], "created_at": row[5],
            }
        finally:
            conn.close()

    def get_student_credentials_by_enrollment_number(self, enrollment_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a student row including authentication columns (password_hash,
        requires_password_change). Used by the unified login lookup.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            enum = clean_str(enrollment_number).strip()
            cols = ("id, enrollment_number, name, password_hash, requires_password_change, "
                    "college_id, team_id, created_at")
            if self.mode == "postgresql":
                cur.execute(f"SELECT {cols} FROM students WHERE enrollment_number = %s;", (enum,))
            else:
                cur.execute(f"SELECT {cols} FROM students WHERE enrollment_number = ?;", (enum,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "enrollment_number": row[1], "name": row[2],
                "password_hash": row[3], "requires_password_change": row[4],
                "college_id": row[5], "team_id": row[6], "created_at": row[7],
            }
        finally:
            conn.close()

    def get_student_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a student by primary key, including authentication columns."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            sid = clean_str(id)
            cols = ("id, enrollment_number, name, password_hash, requires_password_change, "
                    "college_id, team_id, created_at")
            if self.mode == "postgresql":
                cur.execute(f"SELECT {cols} FROM students WHERE id = %s;", (sid,))
            else:
                cur.execute(f"SELECT {cols} FROM students WHERE id = ?;", (sid,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "enrollment_number": row[1], "name": row[2],
                "password_hash": row[3], "requires_password_change": row[4],
                "college_id": row[5], "team_id": row[6], "created_at": row[7],
            }
        finally:
            conn.close()

    def update_student(self, id: str, **fields) -> None:
        """Update a subset of fields on a student record (password rotation, flags)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {"name", "enrollment_number", "password_hash", "requires_password_change",
                       "college_id", "team_id"}
            updates = {}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    if key == "requires_password_change":
                        updates[key] = _as_bool_flag(value)
                    else:
                        updates[key] = clean_str(value)
            if not updates:
                return

            sid = clean_str(id)
            if self.mode == "postgresql":
                set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
                params = list(updates.values()) + [sid]
                cur.execute(f"UPDATE students SET {set_clause} WHERE id = %s;", params)
            else:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                params = list(updates.values()) + [sid]
                cur.execute(f"UPDATE students SET {set_clause} WHERE id = ?;", params)
            conn.commit()
        finally:
            conn.close()
