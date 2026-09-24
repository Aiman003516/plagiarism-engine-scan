import os
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager
import zlib
import base64
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from psycopg2.extras import RealDictCursor
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

class SystemDBStore:
    """
    Production PostgreSQL Relational Storage Manager.
    Automatically creates the 'plagiarism_engine_db' database on local PostgreSQL,
    persisting projects, research papers, keywords, files, and plagiarism scan reports.
    """

    def __init__(self, pg_connection_string: Optional[str] = None, sqlite_db_path: str = "./system_db.sqlite"):
        self.pg_conn_str = pg_connection_string or os.getenv("DATABASE_URL") or DEFAULT_PG_URL
        self.sqlite_path = sqlite_db_path
        self.mode = "sqlite"

        if HAS_PSYCOPG2:
            try:
                self._ensure_pg_database_exists()
                conn = psycopg2.connect(self.pg_conn_str)
                conn.close()
                self.mode = "postgresql"
            except Exception:
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
            return psycopg2.connect(self.pg_conn_str)
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            return conn

    def _init_schema(self):
        """Initializes relational tables for projects, research papers, files, scan audit reports, and fingerprint index."""
        conn = self._get_connection()
        cur = conn.cursor()

        if self.mode == "postgresql":
            cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS papers (
                id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                author VARCHAR(255),
                keywords TEXT,
                extracted_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS project_files (
                id VARCHAR(255) PRIMARY KEY,
                project_id VARCHAR(255) REFERENCES projects(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL,
                file_type VARCHAR(50),
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scan_reports (
                id VARCHAR(255) PRIMARY KEY,
                query_id VARCHAR(255) NOT NULL,
                target_id VARCHAR(255) NOT NULL,
                similarity_score FLOAT NOT NULL,
                match_type VARCHAR(50) NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS fingerprint_index (
                id SERIAL PRIMARY KEY,
                fingerprint_hash BIGINT NOT NULL,
                file_path TEXT NOT NULL,
                project_id VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                position INTEGER DEFAULT 0,
                UNIQUE(fingerprint_hash, file_path, project_id)
            );
            CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
            CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at);
            CREATE INDEX IF NOT EXISTS idx_scan_reports_query_id ON scan_reports(query_id);
            CREATE INDEX IF NOT EXISTS idx_project_files_project_id ON project_files(project_id);
            CREATE INDEX IF NOT EXISTS idx_fp_hash ON fingerprint_index(fingerprint_hash);
            CREATE INDEX IF NOT EXISTS idx_fp_project ON fingerprint_index(project_id);

            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'college_admin',
                college_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS students (
                id VARCHAR(255) PRIMARY KEY,
                enrollment_number VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                college_id VARCHAR(255),
                team_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_students_enrollment ON students(enrollment_number);
            CREATE TABLE IF NOT EXISTS teams (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                college_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_teams_college ON teams(college_id);
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(255) PRIMARY KEY,
                value TEXT
            );
            """)

            # Expand projects table with new metadata columns (safe for existing DBs)
            alter_statements = [
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS title VARCHAR(500);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS abstract TEXT;",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_id VARCHAR(255);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS department VARCHAR(255);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS year INTEGER;",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS university VARCHAR(255);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'Indexed';",
            ]
            for stmt in alter_statements:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass

            self._init_default_settings(cur)

        else:
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT,
                keywords TEXT,
                extracted_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS project_files (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                relative_path TEXT NOT NULL,
                file_type TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS scan_reports (
                id TEXT PRIMARY KEY,
                query_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                similarity_score REAL NOT NULL,
                match_type TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS fingerprint_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint_hash INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                project_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                UNIQUE(fingerprint_hash, file_path, project_id)
            );
            CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
            CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at);
            CREATE INDEX IF NOT EXISTS idx_scan_reports_query_id ON scan_reports(query_id);
            CREATE INDEX IF NOT EXISTS idx_project_files_project_id ON project_files(project_id);
            CREATE INDEX IF NOT EXISTS idx_fp_hash ON fingerprint_index(fingerprint_hash);
            CREATE INDEX IF NOT EXISTS idx_fp_project ON fingerprint_index(project_id);

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'college_admin',
                college_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                enrollment_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                college_id TEXT,
                team_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
            CREATE INDEX IF NOT EXISTS idx_students_enrollment ON students(enrollment_number);
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                college_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_teams_college ON teams(college_id);
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)

            # Expand projects table with new metadata columns (safe for existing DBs)
            alter_statements = [
                "ALTER TABLE projects ADD COLUMN title TEXT;",
                "ALTER TABLE projects ADD COLUMN abstract TEXT;",
                "ALTER TABLE projects ADD COLUMN team_id TEXT;",
                "ALTER TABLE projects ADD COLUMN department TEXT;",
                "ALTER TABLE projects ADD COLUMN year INTEGER;",
                "ALTER TABLE projects ADD COLUMN university TEXT;",
                "ALTER TABLE projects ADD COLUMN status TEXT DEFAULT 'Indexed';",
            ]
            for stmt in alter_statements:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass

            self._init_default_settings(cur)

        conn.commit()
        conn.close()

    def save_paper(self, paper_id: str, title: str, author: str, keywords: str, text: str) -> None:
        """Save or update a research paper record in PostgreSQL."""
        conn = self._get_connection()
        cur = conn.cursor()
        pid, ptitle, pauthor, pkw, ptext = clean_str(paper_id), clean_str(title), clean_str(author), clean_str(keywords), clean_str(text)

        if self.mode == "postgresql":
            cur.execute("""
                INSERT INTO papers (id, title, author, keywords, extracted_text)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, keywords=EXCLUDED.keywords, extracted_text=EXCLUDED.extracted_text;
            """, (pid, ptitle, pauthor, pkw, ptext))
        else:
            cur.execute("""
                INSERT OR REPLACE INTO papers (id, title, author, keywords, extracted_text)
                VALUES (?, ?, ?, ?, ?);
            """, (pid, ptitle, pauthor, pkw, ptext))
        conn.commit()
        conn.close()

    def save_project(self, project_id: str, project_name: str, files: List[Dict[str, Any]]) -> None:
        """Save a project folder and its core files to PostgreSQL or SQLite using bulk batch inserts."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            pid, pname = clean_str(project_id), clean_str(project_name)

            file_rows = []
            for f in files:
                rel_path = clean_str(f.get('relative_path', f.get('filename', '')))
                file_id = clean_str(f"{pid}::{rel_path}")
                f_type = clean_str(f.get('file_type', ''))
                f_content = compress_text(clean_str(f.get('content', '')))
                file_rows.append((file_id, pid, rel_path, f_type, f_content))

            if self.mode == "postgresql":
                cur.execute("INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;", (pid, pname))
                if file_rows:
                    cur.executemany("""
                        INSERT INTO project_files (id, project_id, relative_path, file_type, content)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET content=EXCLUDED.content;
                    """, file_rows)
            else:
                cur.execute("INSERT OR REPLACE INTO projects (id, name) VALUES (?, ?);", (pid, pname))
                if file_rows:
                    cur.executemany("""
                        INSERT OR REPLACE INTO project_files (id, project_id, relative_path, file_type, content)
                        VALUES (?, ?, ?, ?, ?);
                    """, file_rows)
            conn.commit()
        finally:
            conn.close()

    def save_scan_report(self, report_id: str, query_id: str, target_id: str, score: float, match_type: str, details: str) -> None:
        """Save a scan audit report record."""
        conn = self._get_connection()
        cur = conn.cursor()
        rid, qid, tid, mtype, det = clean_str(report_id), clean_str(query_id), clean_str(target_id), clean_str(match_type), clean_str(details)

        if self.mode == "postgresql":
            cur.execute("""
                INSERT INTO scan_reports (id, query_id, target_id, similarity_score, match_type, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET similarity_score=EXCLUDED.similarity_score, details=EXCLUDED.details;
            """, (rid, qid, tid, score, mtype, det))
        else:
            cur.execute("""
                INSERT OR REPLACE INTO scan_reports (id, query_id, target_id, similarity_score, match_type, details)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (rid, qid, tid, score, mtype, det))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Users (JWT auth / RBAC)
    # ------------------------------------------------------------------
    def create_user(self, id: str, name: str, email: str, password_hash: str, role: str, college_id: Optional[str]) -> None:
        """Insert a new user account."""
        conn = self._get_connection()
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
        conn.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch a user by email, or None if not found."""
        conn = self._get_connection()
        cur = conn.cursor()
        uemail = clean_str(email).lower()
        if self.mode == "postgresql":
            cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE email = %s;", (uemail,))
        else:
            cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE email = ?;", (uemail,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return dict(row)
        return {
            "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
            "role": row[4], "college_id": row[5], "created_at": row[6],
        }

    def get_user_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a user by id, or None if not found."""
        conn = self._get_connection()
        cur = conn.cursor()
        uid = clean_str(id)
        if self.mode == "postgresql":
            cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE id = %s;", (uid,))
        else:
            cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE id = ?;", (uid,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return dict(row)
        return {
            "id": row[0], "name": row[1], "email": row[2], "password_hash": row[3],
            "role": row[4], "college_id": row[5], "created_at": row[6],
        }

    def get_all_users(self, role_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all users, optionally filtered by role."""
        conn = self._get_connection()
        cur = conn.cursor()
        if role_filter:
            rrole = clean_str(role_filter)
            if self.mode == "postgresql":
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE role = %s ORDER BY created_at DESC;", (rrole,))
            else:
                cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users WHERE role = ? ORDER BY created_at DESC;", (rrole,))
        else:
            cur.execute("SELECT id, name, email, password_hash, role, college_id, created_at FROM users ORDER BY created_at DESC;")
        rows = cur.fetchall()
        conn.close()

        users = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                users.append(dict(r))
            else:
                users.append({
                    "id": r[0], "name": r[1], "email": r[2], "password_hash": r[3],
                    "role": r[4], "college_id": r[5], "created_at": r[6],
                })
        return users

    def update_user(self, id: str, **fields) -> None:
        """Update a subset of fields on a user record."""
        conn = self._get_connection()
        cur = conn.cursor()
        allowed = {"name", "email", "password_hash", "role", "college_id"}
        updates = {}
        for key, value in fields.items():
            if key in allowed and value is not None:
                if key == "email":
                    updates[key] = clean_str(value).lower()
                else:
                    updates[key] = clean_str(value)
        if not updates:
            conn.close()
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
        conn.close()

    def delete_user(self, id: str) -> None:
        """Delete a user account by id."""
        conn = self._get_connection()
        cur = conn.cursor()
        uid = clean_str(id)
        if self.mode == "postgresql":
            cur.execute("DELETE FROM users WHERE id = %s;", (uid,))
        else:
            cur.execute("DELETE FROM users WHERE id = ?;", (uid,))
        conn.commit()
        conn.close()


    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------
    def create_team(self, team_id: str, name: str, college_id: Optional[str]) -> None:
        """Insert a new team."""
        conn = self._get_connection()
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
        conn.close()

    def get_all_teams(self, college_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all teams, optionally filtered by college_id."""
        conn = self._get_connection()
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
        conn.close()

        teams = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                teams.append(dict(r))
            else:
                teams.append({"id": r[0], "name": r[1], "college_id": r[2], "created_at": r[3]})
        return teams

    def get_team_by_id(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single team by id, or None if not found."""
        conn = self._get_connection()
        cur = conn.cursor()
        tid = clean_str(team_id)
        if self.mode == "postgresql":
            cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE id = %s;", (tid,))
        else:
            cur.execute("SELECT id, name, college_id, created_at FROM teams WHERE id = ?;", (tid,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return dict(row)
        return {"id": row[0], "name": row[1], "college_id": row[2], "created_at": row[3]}

    def update_team(self, team_id: str, **fields) -> None:
        """Update a subset of fields on a team record."""
        conn = self._get_connection()
        cur = conn.cursor()
        allowed = {"name", "college_id"}
        updates = {k: clean_str(v) for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            conn.close()
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
        conn.close()

    def delete_team(self, team_id: str) -> None:
        """Delete a team by id."""
        conn = self._get_connection()
        cur = conn.cursor()
        tid = clean_str(team_id)
        if self.mode == "postgresql":
            cur.execute("DELETE FROM teams WHERE id = %s;", (tid,))
        else:
            cur.execute("DELETE FROM teams WHERE id = ?;", (tid,))
        conn.commit()
        conn.close()

    def add_team_member(self, team_id: str, student_id: str) -> None:
        """Link a student to a team by updating students.team_id."""
        conn = self._get_connection()
        cur = conn.cursor()
        tid = clean_str(team_id)
        sid = clean_str(student_id)
        if self.mode == "postgresql":
            cur.execute("UPDATE students SET team_id = %s WHERE id = %s;", (tid, sid))
        else:
            cur.execute("UPDATE students SET team_id = ? WHERE id = ?;", (tid, sid))
        conn.commit()
        conn.close()

    def remove_team_member(self, student_id: str) -> None:
        """Unlink a student from any team by clearing students.team_id."""
        conn = self._get_connection()
        cur = conn.cursor()
        sid = clean_str(student_id)
        if self.mode == "postgresql":
            cur.execute("UPDATE students SET team_id = NULL WHERE id = %s;", (sid,))
        else:
            cur.execute("UPDATE students SET team_id = NULL WHERE id = ?;", (sid,))
        conn.commit()
        conn.close()

    def get_team_members(self, team_id: str) -> List[Dict[str, Any]]:
        """Fetch all students assigned to a given team."""
        conn = self._get_connection()
        cur = conn.cursor()
        tid = clean_str(team_id)
        if self.mode == "postgresql":
            cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE team_id = %s ORDER BY created_at DESC;", (tid,))
        else:
            cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE team_id = ? ORDER BY created_at DESC;", (tid,))
        rows = cur.fetchall()
        conn.close()

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

    def get_student_by_enrollment_number(self, enrollment_number: str) -> Optional[Dict[str, Any]]:
        """Fetch a student by enrollment number (used for team member lookup)."""
        conn = self._get_connection()
        cur = conn.cursor()
        enum = clean_str(enrollment_number)
        if self.mode == "postgresql":
            cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE enrollment_number = %s;", (enum,))
        else:
            cur.execute("SELECT id, enrollment_number, name, college_id, team_id, created_at FROM students WHERE enrollment_number = ?;", (enum,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return dict(row)
        return {
            "id": row[0], "enrollment_number": row[1], "name": row[2],
            "college_id": row[3], "team_id": row[4], "created_at": row[5],
        }

    def get_all_papers(self) -> List[Dict[str, Any]]:
        """Retrieve all stored research papers from PostgreSQL."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title, author, keywords, extracted_text FROM papers;")
        rows = cur.fetchall()
        conn.close()

        papers = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                papers.append(dict(r))
            else:
                papers.append({"id": r[0], "title": r[1], "author": r[2], "keywords": r[3], "content": r[4], "filename": r[1]})
        return papers

    def get_all_projects(self, page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve all stored projects with full metadata."""
        conn = self._get_connection()
        cur = conn.cursor()
        offset = (page - 1) * limit

        if self.mode == "postgresql":
            cur.execute(
                "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at "
                "FROM projects ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                (limit, offset),
            )
        else:
            cur.execute(
                "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at "
                "FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )

        rows = cur.fetchall()
        conn.close()

        projects = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                projects.append(dict(r))
            else:
                projects.append({
                    "id": r[0], "name": r[1], "title": r[2], "abstract": r[3],
                    "team_id": r[4], "department": r[5], "year": r[6],
                    "university": r[7], "status": r[8], "created_at": r[9],
                })
        return projects

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single project by id."""
        conn = self._get_connection()
        cur = conn.cursor()
        pid = clean_str(project_id)
        if self.mode == "postgresql":
            cur.execute(
                "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at "
                "FROM projects WHERE id = %s;",
                (pid,),
            )
        else:
            cur.execute(
                "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at "
                "FROM projects WHERE id = ?;",
                (pid,),
            )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return dict(row)
        return {
            "id": row[0], "name": row[1], "title": row[2], "abstract": row[3],
            "team_id": row[4], "department": row[5], "year": row[6],
            "university": row[7], "status": row[8], "created_at": row[9],
        }

    def update_project(self, project_id: str, **fields) -> None:
        """Update a subset of fields on a project record."""
        conn = self._get_connection()
        cur = conn.cursor()
        allowed = {"name", "title", "abstract", "team_id", "department", "year", "university", "status"}
        updates = {}
        for key, value in fields.items():
            if key in allowed and value is not None:
                if key == "year":
                    updates[key] = value
                else:
                    updates[key] = clean_str(value)
        if not updates:
            conn.close()
            return

        pid = clean_str(project_id)
        if self.mode == "postgresql":
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            params = list(updates.values()) + [pid]
            cur.execute(f"UPDATE projects SET {set_clause} WHERE id = %s;", params)
        else:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            params = list(updates.values()) + [pid]
            cur.execute(f"UPDATE projects SET {set_clause} WHERE id = ?;", params)
        conn.commit()
        conn.close()

    def delete_project(self, project_id: str) -> None:
        """Delete a project and cascade to its files and fingerprints."""
        conn = self._get_connection()
        cur = conn.cursor()
        pid = clean_str(project_id)
        if self.mode == "postgresql":
            cur.execute("DELETE FROM fingerprint_index WHERE project_id = %s;", (pid,))
            cur.execute("DELETE FROM project_files WHERE project_id = %s;", (pid,))
            cur.execute("DELETE FROM projects WHERE id = %s;", (pid,))
        else:
            cur.execute("DELETE FROM fingerprint_index WHERE project_id = ?;", (pid,))
            cur.execute("DELETE FROM project_files WHERE project_id = ?;", (pid,))
            cur.execute("DELETE FROM projects WHERE id = ?;", (pid,))
        conn.commit()
        conn.close()

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve all files for a given project, decompressing the content."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        if self.mode == "postgresql":
            cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = %s;", (project_id,))
        else:
            cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = ?;", (project_id,))
            
        rows = cur.fetchall()
        conn.close()

        files = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                files.append({
                    "project_id": r['project_id'],
                    "relative_path": r['relative_path'],
                    "file_type": r['file_type'],
                    "content": decompress_text(r['content'])
                })
            else:
                files.append({
                    "project_id": r[0],
                    "relative_path": r[1],
                    "file_type": r[2],
                    "content": decompress_text(r[3])
                })
        return files

    def get_files_by_paths(self, project_id: str, relative_paths: List[str]) -> List[Dict[str, Any]]:
        """Retrieve specific files from another project, decompressing their content."""
        if not relative_paths:
            return []
            
        conn = self._get_connection()
        cur = conn.cursor()
        
        if self.mode == "postgresql":
            placeholders = ','.join(['%s'] * len(relative_paths))
            query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != %s"
            params = tuple(relative_paths) + (project_id,)
            cur.execute(query, params)
        else:
            placeholders = ','.join(['?'] * len(relative_paths))
            query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != ?"
            params = tuple(relative_paths) + (project_id,)
            cur.execute(query, params)
            
        rows = cur.fetchall()
        conn.close()

        files = []
        for r in rows:
            if isinstance(r, dict) or hasattr(r, 'keys'):
                files.append({
                    "project_id": r['project_id'],
                    "relative_path": r['relative_path'],
                    "file_type": r.get('file_type', ''),
                    "content": decompress_text(r['content'])
                })
            else:
                files.append({
                    "project_id": r[0],
                    "relative_path": r[1],
                    "file_type": r[2] if len(r) > 2 else '',
                    "content": decompress_text(r[3])
                })
        return files

    def get_project_fingerprints(self, project_id: str) -> Dict[str, List[Tuple[int, int]]]:
        """Fetch all fingerprints for a given project, grouped by file_path."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        if self.mode == "postgresql":
            cur.execute("SELECT file_path, fingerprint_hash, position FROM fingerprint_index WHERE project_id = %s;", (project_id,))
        else:
            cur.execute("SELECT file_path, fingerprint_hash, position FROM fingerprint_index WHERE project_id = ?;", (project_id,))
            
        rows = cur.fetchall()
        conn.close()

        fp_dict = {}
        for r in rows:
            fpath = r['file_path'] if isinstance(r, dict) or hasattr(r, 'keys') else r[0]
            fhash = r['fingerprint_hash'] if isinstance(r, dict) or hasattr(r, 'keys') else r[1]
            fpos = r['position'] if isinstance(r, dict) or hasattr(r, 'keys') else r[2]
            
            if fpath not in fp_dict:
                fp_dict[fpath] = []
            fp_dict[fpath].append((fhash, fpos))
            
        return fp_dict

    def check_project_exists(self, project_names: list[str]) -> list[str]:
        """Check which project names already exist in the database."""
        if not project_names:
            return []
            
        conn = self._get_connection()
        cur = conn.cursor()
        
        if self.mode == "postgresql":
            placeholders = ','.join(['%s'] * len(project_names))
            cur.execute(f"SELECT name FROM projects WHERE name IN ({placeholders})", tuple(project_names))
        else:
            placeholders = ','.join(['?'] * len(project_names))
            cur.execute(f"SELECT name FROM projects WHERE name IN ({placeholders})", tuple(project_names))
            
        rows = cur.fetchall()
        conn.close()
        
        return [row[0] if not (isinstance(row, dict) or hasattr(row, 'keys')) else row['name'] for row in rows]

    def wipe_all_data(self):
        """Nuclear reset: drops all tables and recreates clean schema."""
        conn = self._get_connection()
        cur = conn.cursor()
        for table in ['fingerprint_index', 'scan_reports', 'project_files', 'papers', 'projects']:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;" if self.mode == "postgresql" else f"DROP TABLE IF EXISTS {table};")
        conn.commit()
        conn.close()
        self._init_schema()

    def store_fingerprints(self, project_id: str, file_path: str, file_type: str, fingerprints: list) -> None:
        """Store computed fingerprints for a file."""
        if not fingerprints:
            return
            
        conn = self._get_connection()
        cur = conn.cursor()
        pid = project_id
        fpath = file_path
        ftype = file_type

        rows = []
        for fp_hash, pos in fingerprints:
            rows.append((fp_hash, fpath, pid, ftype, pos))

        if self.mode == "postgresql":
            cur.executemany("INSERT INTO fingerprint_index (fingerprint_hash, file_path, project_id, file_type, position) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;", rows)
        else:
            cur.executemany("INSERT OR IGNORE INTO fingerprint_index (fingerprint_hash, file_path, project_id, file_type, position) VALUES (?, ?, ?, ?, ?);", rows)
            
        conn.commit()
        conn.close()

    def query_candidates(self, fingerprints: list, file_type: str, exclude_project: str) -> dict:
        """
        Query index for files that share fingerprints.
        Returns a dictionary of {file_path: shared_count}
        """
        if not fingerprints:
            return {}
            
        conn = self._get_connection()
        cur = conn.cursor()
        
        candidates = {}
        # Chunk queries to avoid SQLite/PG limits on IN clause
        chunk_size = 900
        for i in range(0, len(fingerprints), chunk_size):
            chunk = fingerprints[i:i+chunk_size]
            placeholders = ','.join(['%s'] * len(chunk)) if self.mode == "postgresql" else ','.join(['?'] * len(chunk))
            
            params = tuple(chunk) + (file_type, exclude_project)
            query = f"SELECT project_id, file_path, COUNT(*) FROM fingerprint_index WHERE fingerprint_hash IN ({placeholders}) AND file_type = %s AND project_id != %s GROUP BY project_id, file_path;" if self.mode == "postgresql" else f"SELECT project_id, file_path, COUNT(*) FROM fingerprint_index WHERE fingerprint_hash IN ({placeholders}) AND file_type = ? AND project_id != ? GROUP BY project_id, file_path;"
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            for row in rows:
                if isinstance(row, dict) or hasattr(row, 'keys'):
                    pid = row['project_id']
                    fpath = row['file_path']
                    count = row.get('count', row.get('COUNT(*)', 0))
                else:
                    pid = row[0]
                    fpath = row[1]
                    count = row[2]
                key = f"{pid}::{fpath}"
                candidates[key] = candidates.get(key, 0) + count
                
        conn.close()
        return candidates

    def delete_project_fingerprints(self, project_id: str):
        conn = self._get_connection()
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("DELETE FROM fingerprint_index WHERE project_id = %s", (project_id,))
        else:
            cur.execute("DELETE FROM fingerprint_index WHERE project_id = ?", (project_id,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Counts (dashboard)
    # ------------------------------------------------------------------
    def count_projects(self) -> int:
        """Return the total number of projects."""
        conn = self._get_connection()
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("SELECT COUNT(*) FROM projects;")
        else:
            cur.execute("SELECT COUNT(*) FROM projects;")
        row = cur.fetchone()
        conn.close()
        if not row:
            return 0
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return int(row.get('count', row.get('COUNT(*)', 0)))
        return int(row[0])

    def count_teams(self) -> int:
        """Return the total number of teams."""
        conn = self._get_connection()
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("SELECT COUNT(*) FROM teams;")
        else:
            cur.execute("SELECT COUNT(*) FROM teams;")
        row = cur.fetchone()
        conn.close()
        if not row:
            return 0
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return int(row.get('count', row.get('COUNT(*)', 0)))
        return int(row[0])

    def count_users(self) -> int:
        """Return the total number of users."""
        conn = self._get_connection()
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("SELECT COUNT(*) FROM users;")
        else:
            cur.execute("SELECT COUNT(*) FROM users;")
        row = cur.fetchone()
        conn.close()
        if not row:
            return 0
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return int(row.get('count', row.get('COUNT(*)', 0)))
        return int(row[0])

    def count_files(self) -> int:
        """Return the total number of project files."""
        conn = self._get_connection()
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("SELECT COUNT(*) FROM project_files;")
        else:
            cur.execute("SELECT COUNT(*) FROM project_files;")
        row = cur.fetchone()
        conn.close()
        if not row:
            return 0
        if isinstance(row, dict) or hasattr(row, 'keys'):
            return int(row.get('count', row.get('COUNT(*)', 0)))
        return int(row[0])

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
        cur = conn.cursor()
        if self.mode == "postgresql":
            cur.execute("SELECT key, value FROM settings;")
        else:
            cur.execute("SELECT key, value FROM settings;")
        rows = cur.fetchall()
        conn.close()

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

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Bulk update settings. Values are JSON-encoded before storage."""
        conn = self._get_connection()
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
        conn.close()
