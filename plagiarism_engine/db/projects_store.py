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
        """Save a project folder and its core files using StorageService and Postgres metadata."""
        from plagiarism_engine.storage import get_storage_service
        storage = get_storage_service()

        conn = self._get_connection()
        try:
            cur = conn.cursor()
            pid, pname = clean_str(project_id), clean_str(project_name)

            file_rows = []
            for f in files:
                rel_path = clean_str(f.get('relative_path', f.get('filename', '')))
                file_id = clean_str(f"{pid}::{rel_path}")
                f_type = clean_str(f.get('file_type', ''))
                f_content = clean_str(f.get('content', ''))
                
                # Save actual content to Cloud/Local Storage
                storage_path = f"{pid}/{rel_path}"
                storage.save_file(storage_path, f_content.encode('utf-8'))
                
                # We store empty content in DB to save space, rely on StorageService
                empty_content = compress_text("")
                file_rows.append((file_id, pid, rel_path, f_type, empty_content))

            if self.mode == "postgresql":
                cur.execute("INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;", (pid, pname))
                if file_rows:
                    new_rel_paths = [r[2] for r in file_rows]
                    # Clean up deleted files from previous upload
                    cur.execute("DELETE FROM project_files WHERE project_id = %s AND relative_path != ALL(%s);", (pid, new_rel_paths))
                    cur.executemany("""
                        INSERT INTO project_files (id, project_id, relative_path, file_type, content)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET file_type=EXCLUDED.file_type, embedding_binary=NULL, embedding=NULL;
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
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id, review_notes, submitted_by_student_id, university_id, college_id, department_id "
                    "FROM projects ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                    (limit, offset),
                )
            else:
                cur.execute(
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id, review_notes, submitted_by_student_id, university_id, college_id, department_id "
                    "FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    (limit, offset),
                )

            rows = cur.fetchall()

            projects = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    item = dict(r)
                    if item.get("abstract"):
                        item["abstract"] = decompress_text(item["abstract"])
                    projects.append(item)
                else:
                    projects.append({
                        "id": r[0], "name": r[1], "title": r[2], "abstract": decompress_text(r[3]) if r[3] else "",
                        "team_id": r[4], "department": r[5], "year": r[6],
                        "university": r[7], "status": r[8], "created_at": r[9],
                        "student_id": r[10],
                        "review_notes": r[11] if len(r) > 11 else None,
                        "submitted_by_student_id": r[12] if len(r) > 12 else None,
                    })
            return projects
        finally:
            conn.close()

    def get_all_project_names(self) -> List[str]:
        """Retrieve only the names of all projects for fast stats calculation."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM projects;")
            rows = cur.fetchall()
            names = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    val = r.get('name', '')
                else:
                    val = r[0] if r else ''
                if val:
                    names.append(val)
            return names
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
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id, review_notes, submitted_by_student_id, university_id, college_id, department_id "
                    "FROM projects WHERE id = %s;",
                    (pid,),
                )
            else:
                cur.execute(
                    "SELECT id, name, title, abstract, team_id, department, year, university, status, created_at, student_id, review_notes, submitted_by_student_id, university_id, college_id, department_id "
                    "FROM projects WHERE id = ?;",
                    (pid,),
                )
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict) or hasattr(row, 'keys'):
                item = dict(row)
                if item.get("abstract"):
                    item["abstract"] = decompress_text(item["abstract"])
                return item
            return {
                "id": row[0], "name": row[1], "title": row[2], "abstract": decompress_text(row[3]) if row[3] else "",
                "team_id": row[4], "department": row[5], "year": row[6],
                "university": row[7], "status": row[8], "created_at": row[9],
                "student_id": row[10] if len(row) > 10 else None,
                "review_notes": row[11] if len(row) > 11 else None,
                "submitted_by_student_id": row[12] if len(row) > 12 else None,
                "university_id": row[13] if len(row) > 13 else None,
                "college_id": row[14] if len(row) > 14 else None,
                "department_id": row[15] if len(row) > 15 else None,
            }
        finally:
            conn.close()

    def update_project(self, project_id: str, **fields) -> None:
        """Update a subset of fields on a project record."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            allowed = {
                "name", "title", "abstract", "team_id", "department", "year", "university", "status",
                "university_id", "college_id", "department_id", "student_id", "submitted_by_student_id",
                "review_notes", "abstract_embedding", "abstract_embedding_binary"
            }
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
        """Delete a project and cascade to its files and fingerprints. Also deletes files from StorageService."""
        from plagiarism_engine.storage import get_storage_service
        storage = get_storage_service()

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
            
            # Delete physical files from Cloud/Local Storage
            try:
                storage.delete_directory(pid)
            except Exception as e:
                print(f"Warning: Failed to delete storage directory for {pid}: {e}")
                
            conn.commit()
        finally:
            conn.close()

    def get_project_files(self, project_id: str, include_content: bool = True) -> List[Dict[str, Any]]:
        """Retrieve all files for a given project, fetching content from StorageService with DB fallback."""
        pid = clean_str(project_id)
        if not include_content:
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if self.mode == "postgresql":
                    cur.execute("SELECT project_id, relative_path, file_type FROM project_files WHERE project_id = %s;", (pid,))
                else:
                    cur.execute("SELECT project_id, relative_path, file_type FROM project_files WHERE project_id = ?;", (pid,))
                rows = cur.fetchall()
                files = []
                for r in rows:
                    if isinstance(r, dict) or hasattr(r, 'keys'):
                        files.append({
                            "project_id": r['project_id'],
                            "relative_path": r['relative_path'],
                            "file_type": r['file_type'],
                            "content": ""
                        })
                    else:
                        files.append({
                            "project_id": r[0],
                            "relative_path": r[1],
                            "file_type": r[2],
                            "content": ""
                        })
                return files
            finally:
                conn.close()

        from plagiarism_engine.storage import get_storage_service
        storage = get_storage_service()

        conn = self._get_connection()
        try:
            cur = conn.cursor()
        
            if self.mode == "postgresql":
                cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = %s;", (pid,))
            else:
                cur.execute("SELECT project_id, relative_path, file_type, content FROM project_files WHERE project_id = ?;", (pid,))
            
            rows = cur.fetchall()

            files = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    pid = r['project_id']
                    rel_path = r['relative_path']
                    ftype = r['file_type']
                    raw_db_content = r.get('content', '') if isinstance(r, dict) else r['content']
                else:
                    pid = r[0]
                    rel_path = r[1]
                    ftype = r[2]
                    raw_db_content = r[3] if len(r) > 3 else ''
                
                storage_path = f"{pid}/{rel_path}"
                content = ""
                try:
                    content = storage.read_file(storage_path).decode('utf-8', errors='replace')
                except Exception:
                    if raw_db_content:
                        try:
                            content = decompress_text(raw_db_content)
                        except Exception:
                            content = ""

                files.append({
                    "project_id": pid,
                    "relative_path": rel_path,
                    "file_type": ftype,
                    "content": content
                })
            return files
        finally:
            conn.close()

    def get_files_by_paths(
        self,
        project_id: str,
        relative_paths: List[str],
        target_project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve specific files from another project, fetching content from StorageService with DB fallback."""
        if not relative_paths:
            return []
            
        from plagiarism_engine.storage import get_storage_service
        storage = get_storage_service()

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
                    if target_project_id:
                        query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id = %s"
                        params = tuple(chunk) + (target_project_id,)
                    else:
                        query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != %s"
                        params = tuple(chunk) + (project_id,)
                else:
                    placeholders = ','.join(['?'] * len(chunk))
                    if target_project_id:
                        query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id = ?"
                        params = tuple(chunk) + (target_project_id,)
                    else:
                        query = f"SELECT project_id, relative_path, file_type, content FROM project_files WHERE relative_path IN ({placeholders}) AND project_id != ?"
                        params = tuple(chunk) + (project_id,)

                cur.execute(query, params)
                rows = cur.fetchall()

                for r in rows:
                    if isinstance(r, dict) or hasattr(r, 'keys'):
                        row_keys = r.keys()
                        pid = r['project_id']
                        rel_path = r['relative_path']
                        ftype = r['file_type'] if 'file_type' in row_keys else ''
                        raw_db_content = r['content'] if 'content' in row_keys else ''
                    else:
                        pid = r[0]
                        rel_path = r[1]
                        ftype = r[2] if len(r) > 2 else ''
                        raw_db_content = r[3] if len(r) > 3 else ''
                    
                    storage_path = f"{pid}/{rel_path}"
                    content = ""
                    try:
                        content = storage.read_file(storage_path).decode('utf-8', errors='replace')
                    except Exception:
                        if raw_db_content:
                            try:
                                content = decompress_text(raw_db_content)
                            except Exception:
                                content = ""

                    files.append({
                        "project_id": pid,
                        "relative_path": rel_path,
                        "file_type": ftype,
                        "content": content
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
