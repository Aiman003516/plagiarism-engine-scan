"""Projects, papers, project files and scan reports."""

from typing import List, Dict, Any, Optional, Tuple

from .helpers import clean_str, compress_text, decompress_text


class ProjectsStoreMixin:
    """Projects, papers, project files and scan reports. Mixed into SystemDBStore."""

    def save_paper(self, paper_id: str, title: str, author: str, keywords: str, text: str) -> None:
        """Save or update a research paper record in PostgreSQL."""
        conn = self._get_connection()
        try:
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
        finally:
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
        try:
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
        finally:
            conn.close()

    def get_all_papers(self) -> List[Dict[str, Any]]:
        """Retrieve all stored research papers from PostgreSQL."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, title, author, keywords, extracted_text FROM papers;")
            rows = cur.fetchall()

            papers = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    papers.append(dict(r))
                else:
                    papers.append({"id": r[0], "title": r[1], "author": r[2], "keywords": r[3], "content": r[4], "filename": r[1]})
            return papers
        finally:
            conn.close()

    def get_all_projects(self, page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve all stored projects with full metadata."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            offset = (page - 1) * limit

            if self.mode == "postgresql":
                cur.execute(
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id "
                    "FROM projects ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                    (limit, offset),
                )
            else:
                cur.execute(
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id "
                    "FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (limit, offset),
                )

            rows = cur.fetchall()

            projects = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    projects.append(dict(r))
                else:
                    projects.append({
                        "id": r[0], "name": r[1], "title": r[2], "abstract": r[3],
                        "team_id": r[4], "department": r[5], "year": r[6],
                        "university": r[7], "status": r[8], "created_at": r[9],
                        "student_id": r[10],
                    })
            return projects
        finally:
            conn.close()

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single project by id."""
        conn = self._get_connection()
        try:
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
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                return dict(row)
            return {
                "id": row[0], "name": row[1], "title": row[2], "abstract": row[3],
                "team_id": row[4], "department": row[5], "year": row[6],
                "university": row[7], "status": row[8], "created_at": row[9],
            }
        finally:
            conn.close()

    def update_project(self, project_id: str, **fields) -> None:
        """Update a subset of fields on a project record."""
        conn = self._get_connection()
        try:
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
        finally:
            conn.close()

    def delete_project(self, project_id: str) -> None:
        """Delete a project and cascade to its files and fingerprints."""
        conn = self._get_connection()
        try:
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
        finally:
            conn.close()

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve all files for a given project, decompressing the content."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
        
            if self.mode == "postgresql":
                cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = %s;", (project_id,))
            else:
                cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = ?;", (project_id,))
            
            rows = cur.fetchall()

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
        finally:
            conn.close()

    def get_files_by_paths(self, project_id: str, relative_paths: List[str]) -> List[Dict[str, Any]]:
        """Retrieve specific files from another project, decompressing their content."""
        if not relative_paths:
            return []
            
        conn = self._get_connection()
        try:
            cur = conn.cursor()

            files = []
            # Chunk queries to avoid SQLite/PG limits on IN clause
            chunk_size = 500
            for i in range(0, len(relative_paths), chunk_size):
                chunk = relative_paths[i:i+chunk_size]

                if self.mode == "postgresql":
                    placeholders = ','.join(['%s'] * len(chunk))
                    query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != %s"
                    params = tuple(chunk) + (project_id,)
                else:
                    placeholders = ','.join(['?'] * len(chunk))
                    query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != ?"
                    params = tuple(chunk) + (project_id,)

                cur.execute(query, params)
                rows = cur.fetchall()

                for r in rows:
                    if isinstance(r, dict) or hasattr(r, 'keys'):
                        row_keys = r.keys()
                        files.append({
                            "project_id": r['project_id'],
                            "relative_path": r['relative_path'],
                            "file_type": r['file_type'] if 'file_type' in row_keys else '',
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
        finally:
            conn.close()

    def get_file_fingerprint_count(self, project_id: str, file_path: str) -> int:
        """Get the total number of fingerprints stored for a specific file."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("SELECT COUNT(*) FROM fingerprint_index WHERE project_id = %s AND file_path = %s", (project_id, file_path))
            else:
                cur.execute("SELECT COUNT(*) FROM fingerprint_index WHERE project_id = ? AND file_path = ?", (project_id, file_path))
            row = cur.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def get_project_fingerprints(self, project_id: str) -> Dict[str, List[Tuple[int, int]]]:
        """Fetch all fingerprints for a given project, grouped by file_path."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
        
            if self.mode == "postgresql":
                cur.execute("SELECT file_path, fingerprint_hash, position FROM fingerprint_index WHERE project_id = %s;", (project_id,))
            else:
                cur.execute("SELECT file_path, fingerprint_hash, position FROM fingerprint_index WHERE project_id = ?;", (project_id,))
            
            rows = cur.fetchall()

            fp_dict = {}
            for r in rows:
                fpath = r['file_path'] if isinstance(r, dict) or hasattr(r, 'keys') else r[0]
                fhash = r['fingerprint_hash'] if isinstance(r, dict) or hasattr(r, 'keys') else r[1]
                fpos = r['position'] if isinstance(r, dict) or hasattr(r, 'keys') else r[2]
            
                if fpath not in fp_dict:
                    fp_dict[fpath] = []
                fp_dict[fpath].append((fhash, fpos))
            
            return fp_dict
        finally:
            conn.close()

    def check_project_exists(self, project_names: list[str]) -> list[str]:
        """Check which project names already exist in the database."""
        if not project_names:
            return []
            
        conn = self._get_connection()
        try:
            cur = conn.cursor()
        
            if self.mode == "postgresql":
                placeholders = ','.join(['%s'] * len(project_names))
                cur.execute(f"SELECT name FROM projects WHERE name IN ({placeholders})", tuple(project_names))
            else:
                placeholders = ','.join(['?'] * len(project_names))
                cur.execute(f"SELECT name FROM projects WHERE name IN ({placeholders})", tuple(project_names))
            
            rows = cur.fetchall()
        
            return [row[0] if not (isinstance(row, dict) or hasattr(row, 'keys')) else row['name'] for row in rows]
        finally:
            conn.close()

    def wipe_all_data(self):
        """Nuclear reset: drops all tables and recreates clean schema."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            for table in ['fingerprint_index', 'scan_reports', 'project_files', 'papers', 'projects']:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;" if self.mode == "postgresql" else f"DROP TABLE IF EXISTS {table};")
            conn.commit()
            self._init_schema()
        finally:
            conn.close()
