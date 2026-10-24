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
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE email = %s;", (uemail,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE email = ?;", (uemail,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
                "role": row[4], "college_id": row[5], "created_at": row[6],
                "requires_password_change": row[7],
                "university_id": row[8] if len(row) > 8 else None,
                "department_id": row[9] if len(row) > 9 else None,
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
            if mapped.get("role") == "student":
                mapped["is_student"] = True
                # Hydrate student details from students table (team_id, enrollment_number)
                std_rec = self.get_student_credentials_by_enrollment_number(ident) or self.get_student_by_id(mapped.get("id"))
                if std_rec:
                    mapped["enrollment_number"] = std_rec.get("enrollment_number", ident)
                    mapped["team_id"] = std_rec.get("team_id")
                    if not mapped.get("college_id"):
                        mapped["college_id"] = std_rec.get("college_id")
                    if not mapped.get("university_id"):
                        mapped["university_id"] = std_rec.get("university_id")
                    if not mapped.get("department_id"):
                        mapped["department_id"] = std_rec.get("department_id")
            else:
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
            "university_id": student.get("university_id"),
            "department_id": student.get("department_id"),
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
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE id = %s;", (uid,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE id = ?;", (uid,))
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
                "role": row[4], "college_id": row[5], "created_at": row[6],
                "requires_password_change": row[7],
                "university_id": row[8] if len(row) > 8 else None,
                "department_id": row[9] if len(row) > 9 else None,
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
                    cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE role = %s ORDER BY created_at DESC;", (rrole,))
                else:
                    cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users WHERE role = ? ORDER BY created_at DESC;", (rrole,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at, requires_password_change, university_id, department_id FROM users ORDER BY created_at DESC;")
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
                        "university_id": r[8] if len(r) > 8 else None,
                        "department_id": r[9] if len(r) > 9 else None,
                    })
            return users
        finally:
            conn.close()

    def update_user(self, id: str, **fields) -> None:
        """Update a subset of fields on a user record."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {"name", "email", "password_hash", "role", "college_id", "requires_password_change", "university_id", "department_id"}
            updates = {}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    if key == "email":
                        updates[key] = clean_str(value).lower()
                    elif key == "requires_password_change":
                        flag = _as_bool_flag(value)
                        updates[key] = bool(flag) if self.mode == "postgresql" else flag
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
        """Delete a user account by id, syncing deletion across both users and students."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            uid = clean_str(id)
            if self.mode == "postgresql":
                cur.execute("DELETE FROM users WHERE id = %s;", (uid,))
                cur.execute("DELETE FROM students WHERE id = %s;", (uid,))
            else:
                cur.execute("DELETE FROM users WHERE id = ?;", (uid,))
                cur.execute("DELETE FROM students WHERE id = ?;", (uid,))
            conn.commit()
        finally:
            conn.close()

    def delete_student(self, id: str) -> None:
        """Delete a student account by id or enrollment number."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            sid = clean_str(id)
            if self.mode == "postgresql":
                cur.execute("DELETE FROM students WHERE id = %s OR enrollment_number = %s;", (sid, sid))
                cur.execute("DELETE FROM users WHERE id = %s OR email = %s;", (sid, sid))
            else:
                cur.execute("DELETE FROM students WHERE id = ? OR enrollment_number = ?;", (sid, sid))
                cur.execute("DELETE FROM users WHERE id = ? OR email = ?;", (sid, sid))
            conn.commit()
        finally:
            conn.close()

    def create_student(self, id: str, enrollment_number: str, name: str, password_hash: str,
                       requires_password_change: bool = True, college_id: Optional[str] = None,
                       university_id: Optional[str] = None, department_id: Optional[str] = None) -> None:
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
            sflag_int = _as_bool_flag(requires_password_change)
            sflag = bool(sflag_int) if self.mode == "postgresql" else sflag_int
            scol = clean_str(college_id) if college_id else None
            suni = clean_str(university_id) if university_id else None
            sdept = clean_str(department_id) if department_id else None

            if self.mode == "postgresql":
                cur.execute("""
                    INSERT INTO students (id, enrollment_number, name, password_hash, requires_password_change, college_id, university_id, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        college_id = COALESCE(EXCLUDED.college_id, students.college_id),
                        university_id = COALESCE(EXCLUDED.university_id, students.university_id),
                        department_id = COALESCE(EXCLUDED.department_id, students.department_id);
                """, (sid, senum, sname, sph, sflag, scol, suni, sdept))
            else:
                cur.execute("""
                    INSERT OR REPLACE INTO students (id, enrollment_number, name, password_hash, requires_password_change, college_id, university_id, department_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (sid, senum, sname, sph, sflag, scol, suni, sdept))
            conn.commit()
        finally:
            conn.close()


    def get_student_by_enrollment_number(self, enrollment_number: str) -> Optional[Dict[str, Any]]:
        """Fetch a student by enrollment number (used for team member lookup)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            enum = clean_str(enrollment_number)
            cols = "id, enrollment_number, name, college_id, team_id, created_at, university_id, department_id"
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
                "college_id": row[3], "team_id": row[4], "created_at": row[5],
                "university_id": row[6] if len(row) > 6 else None,
                "department_id": row[7] if len(row) > 7 else None,
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
                    "college_id, team_id, created_at, university_id, department_id")
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
                "university_id": row[8] if len(row) > 8 else None,
                "department_id": row[9] if len(row) > 9 else None,
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
                    "college_id, team_id, created_at, university_id, department_id")
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
                "university_id": row[8] if len(row) > 8 else None,
                "department_id": row[9] if len(row) > 9 else None,
            }
        finally:
            conn.close()

    def update_student(self, id: str, **fields) -> None:
        """Update a subset of fields on a student record (password rotation, flags, scope)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {"name", "enrollment_number", "password_hash", "requires_password_change",
                       "college_id", "team_id", "university_id", "department_id"}
            updates = {}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    if key == "requires_password_change":
                        flag = _as_bool_flag(value)
                        updates[key] = bool(flag) if self.mode == "postgresql" else flag
                    else:
                        updates[key] = clean_str(value)
            if not updates:
                return

            if self.mode == "postgresql":
                set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(id)]
                cur.execute(f"UPDATE students SET {set_clause} WHERE id = %s;", params)
            else:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                params = list(updates.values()) + [clean_str(id)]
                cur.execute(f"UPDATE students SET {set_clause} WHERE id = ?;", params)
            conn.commit()
        finally:
            conn.close()
