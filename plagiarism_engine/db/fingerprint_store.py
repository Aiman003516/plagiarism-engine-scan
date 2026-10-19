"""Winnowing fingerprint storage and candidate queries."""


from typing import Optional, Iterable, List, Dict, Any, Tuple
from .helpers import row_get


class FingerprintStoreMixin:
    """Winnowing fingerprint storage and candidate queries. Mixed into SystemDBStore."""

    def store_fingerprints(self, project_id: str, file_path: str, file_type: str, fingerprints: list) -> None:
        """Store computed fingerprints for a file."""
        if not fingerprints:
            return
            
        conn = self._get_connection()
        try:
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
        finally:
            conn.close()

    def store_fingerprints_batch(self, project_id: str, batch: list) -> None:
        """Store multiple files' fingerprints in one transaction. batch is list of (file_path, file_type, fingerprints_list)"""
        if not batch:
            return
            
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            rows = []
            for file_path, file_type, fingerprints in batch:
                for fp_hash, pos in fingerprints:
                    rows.append((fp_hash, file_path, project_id, file_type, pos))
                
            if self.mode == "postgresql":
                cur.executemany("INSERT INTO fingerprint_index (fingerprint_hash, file_path, project_id, file_type, position) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;", rows)
            else:
                cur.executemany("INSERT OR IGNORE INTO fingerprint_index (fingerprint_hash, file_path, project_id, file_type, position) VALUES (?, ?, ?, ?, ?);", rows)
            
            conn.commit()
        finally:
            conn.close()

    def query_candidates(self, fingerprints: list, file_type: str, exclude_project: str) -> dict:
        """
        Query index for files that share fingerprints.
        Returns a dictionary of {file_path: shared_count}
        """
        if not fingerprints:
            return {}
            
        conn = self._get_connection()
        try:
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
                        count = row_get(row, 'count', row_get(row, 'COUNT(*)', 0))
                    else:
                        pid = row[0]
                        fpath = row[1]
                        count = row[2]
                    key = f"{pid}::{fpath}"
                    candidates[key] = candidates.get(key, 0) + count
                
            return candidates
        finally:
            conn.close()

    def query_project_candidates(
        self,
        project_id: str,
        max_common_projects: int = 5,
        min_shared: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        One single SQL query per scan to find all (source_file, target_project, target_file)
        lexical candidate matches with MOSS-style suppression of common boilerplate hashes.
        Uses COUNT(DISTINCT fingerprint_hash) to avoid duplicate-hash inflation inside files.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if max_common_projects > 0:
                if self.mode == "postgresql":
                    query = """
                    WITH source_fps AS (
                        SELECT fingerprint_hash, file_path, file_type
                        FROM fingerprint_index
                        WHERE project_id = %s
                    ),
                    common AS (
                        SELECT f.fingerprint_hash
                        FROM fingerprint_index f
                        JOIN (SELECT DISTINCT fingerprint_hash FROM source_fps) s
                          ON f.fingerprint_hash = s.fingerprint_hash
                        GROUP BY f.fingerprint_hash
                        HAVING COUNT(DISTINCT f.project_id) >= %s
                    )
                    SELECT s.file_path, o.project_id, o.file_path AS target_file,
                           COUNT(DISTINCT s.fingerprint_hash) AS shared, s.file_type
                    FROM source_fps s
                    JOIN fingerprint_index o
                      ON o.fingerprint_hash = s.fingerprint_hash AND o.file_type = s.file_type AND o.project_id <> %s
                    WHERE s.fingerprint_hash NOT IN (SELECT fingerprint_hash FROM common)
                    GROUP BY s.file_path, o.project_id, o.file_path, s.file_type
                    HAVING COUNT(DISTINCT s.fingerprint_hash) >= %s;
                    """
                    cur.execute(query, (project_id, max_common_projects, project_id, min_shared))
                else:
                    query = """
                    WITH source_fps AS (
                        SELECT fingerprint_hash, file_path, file_type
                        FROM fingerprint_index
                        WHERE project_id = ?
                    ),
                    common AS (
                        SELECT f.fingerprint_hash
                        FROM fingerprint_index f
                        JOIN (SELECT DISTINCT fingerprint_hash FROM source_fps) s
                          ON f.fingerprint_hash = s.fingerprint_hash
                        GROUP BY f.fingerprint_hash
                        HAVING COUNT(DISTINCT f.project_id) >= ?
                    )
                    SELECT s.file_path, o.project_id, o.file_path AS target_file,
                           COUNT(DISTINCT s.fingerprint_hash) AS shared, s.file_type
                    FROM source_fps s
                    JOIN fingerprint_index o
                      ON o.fingerprint_hash = s.fingerprint_hash AND o.file_type = s.file_type AND o.project_id <> ?
                    WHERE s.fingerprint_hash NOT IN (SELECT fingerprint_hash FROM common)
                    GROUP BY s.file_path, o.project_id, o.file_path, s.file_type
                    HAVING COUNT(DISTINCT s.fingerprint_hash) >= ?;
                    """
                    cur.execute(query, (project_id, max_common_projects, project_id, min_shared))
            else:
                if self.mode == "postgresql":
                    query = """
                    WITH source_fps AS (
                        SELECT fingerprint_hash, file_path, file_type
                        FROM fingerprint_index
                        WHERE project_id = %s
                    )
                    SELECT s.file_path, o.project_id, o.file_path AS target_file,
                           COUNT(DISTINCT s.fingerprint_hash) AS shared, s.file_type
                    FROM source_fps s
                    JOIN fingerprint_index o
                      ON o.fingerprint_hash = s.fingerprint_hash AND o.file_type = s.file_type AND o.project_id <> %s
                    GROUP BY s.file_path, o.project_id, o.file_path, s.file_type
                    HAVING COUNT(DISTINCT s.fingerprint_hash) >= %s;
                    """
                    cur.execute(query, (project_id, project_id, min_shared))
                else:
                    query = """
                    WITH source_fps AS (
                        SELECT fingerprint_hash, file_path, file_type
                        FROM fingerprint_index
                        WHERE project_id = ?
                    )
                    SELECT s.file_path, o.project_id, o.file_path AS target_file,
                           COUNT(DISTINCT s.fingerprint_hash) AS shared, s.file_type
                    FROM source_fps s
                    JOIN fingerprint_index o
                      ON o.fingerprint_hash = s.fingerprint_hash AND o.file_type = s.file_type AND o.project_id <> ?
                    GROUP BY s.file_path, o.project_id, o.file_path, s.file_type
                    HAVING COUNT(DISTINCT s.fingerprint_hash) >= ?;
                    """
                    cur.execute(query, (project_id, project_id, min_shared))

            rows = cur.fetchall()
            results = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    results.append({
                        "source_file": r["file_path"],
                        "target_project": r["project_id"],
                        "target_file": r["target_file"],
                        "shared": int(r["shared"]),
                        "file_type": r["file_type"],
                    })
                else:
                    results.append({
                        "source_file": r[0],
                        "target_project": r[1],
                        "target_file": r[2],
                        "shared": int(r[3]),
                        "file_type": r[4],
                    })
            return results
        finally:
            conn.close()

    def get_file_fingerprint_counts_for_projects(self, project_ids: Iterable[str]) -> Dict[Tuple[str, str], int]:
        """
        Batch-fetches total distinct fingerprint counts for all files in the given projects.
        Returns {(project_id, file_path): count}
        """
        pids = list(set(project_ids))
        if not pids:
            return {}
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            counts: Dict[Tuple[str, str], int] = {}
            chunk_size = 500
            for i in range(0, len(pids), chunk_size):
                chunk = pids[i : i + chunk_size]
                placeholders = ",".join(["%s"] * len(chunk)) if self.mode == "postgresql" else ",".join(["?"] * len(chunk))
                query = f"""
                SELECT project_id, file_path, COUNT(DISTINCT fingerprint_hash) AS cnt
                FROM fingerprint_index
                WHERE project_id IN ({placeholders})
                GROUP BY project_id, file_path;
                """
                cur.execute(query, tuple(chunk))
                rows = cur.fetchall()
                for r in rows:
                    if isinstance(r, dict) or hasattr(r, 'keys'):
                        counts[(r["project_id"], r["file_path"])] = int(r["cnt"])
                    else:
                        counts[(r[0], r[1])] = int(r[2])
            return counts
        finally:
            conn.close()

    def delete_project_fingerprints(self, project_id: str):
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.mode == "postgresql":
                cur.execute("DELETE FROM fingerprint_index WHERE project_id = %s", (project_id,))
            else:
                cur.execute("DELETE FROM fingerprint_index WHERE project_id = ?", (project_id,))
            conn.commit()
        finally:
            conn.close()

    def get_common_fingerprints(self, max_projects: int, candidate_hashes: Optional[Iterable[int]] = None) -> set:
        """Return set of fingerprint_hash that appear in >= max_projects distinct projects (MOSS-style suppression).
        If candidate_hashes is provided, restricts aggregation to those hashes using index lookups.
        """
        if max_projects <= 0:
            return set()
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if candidate_hashes is not None:
                h_list = list(set(candidate_hashes))
                if not h_list:
                    return set()
                common = set()
                chunk_size = 900
                for i in range(0, len(h_list), chunk_size):
                    chunk = h_list[i : i + chunk_size]
                    placeholders = ",".join(["%s"] * len(chunk)) if self.mode == "postgresql" else ",".join(["?"] * len(chunk))
                    query = (
                        f"SELECT fingerprint_hash FROM fingerprint_index WHERE fingerprint_hash IN ({placeholders}) GROUP BY fingerprint_hash HAVING COUNT(DISTINCT project_id) >= %s;"
                        if self.mode == "postgresql"
                        else f"SELECT fingerprint_hash FROM fingerprint_index WHERE fingerprint_hash IN ({placeholders}) GROUP BY fingerprint_hash HAVING COUNT(DISTINCT project_id) >= ?;"
                    )
                    cur.execute(query, tuple(chunk) + (max_projects,))
                    rows = cur.fetchall()
                    for r in rows:
                        val = r[0] if not (isinstance(r, dict) or hasattr(r, 'keys')) else r['fingerprint_hash']
                        common.add(val)
                return common
            else:
                query = (
                    "SELECT fingerprint_hash FROM fingerprint_index GROUP BY fingerprint_hash HAVING COUNT(DISTINCT project_id) >= %s;"
                    if self.mode == "postgresql"
                    else "SELECT fingerprint_hash FROM fingerprint_index GROUP BY fingerprint_hash HAVING COUNT(DISTINCT project_id) >= ?;"
                )
                cur.execute(query, (max_projects,))
                rows = cur.fetchall()
                return {r[0] if not (isinstance(r, dict) or hasattr(r, 'keys')) else r['fingerprint_hash'] for r in rows}
        finally:
            conn.close()

