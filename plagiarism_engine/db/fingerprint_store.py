"""Winnowing fingerprint storage and candidate queries."""


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
