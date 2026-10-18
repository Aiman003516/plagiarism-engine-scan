"""PgVector storage implementation with Binary Quantization & 2-Step Rescoring.

Round 2 changes:
- Every vector row carries `embedding_model` (the model folder that produced it). Rows are only
  ever compared with rows from the *same* model, so zero-padded 384/768/1024-d spaces never mix.
- Search results carry both the raw cosine (`similarity_raw`) and the per-model calibrated
  score (`similarity`), see `plagiarism_engine.fusion_scorer.calibrate_semantic`.
- `search_bulk` is batched: one LATERAL query returns the Hamming Top-100 candidate ids for every
  source file of the project, then each distinct embedding is fetched once and rescored in NumPy.
"""

from typing import List, Dict, Any, Tuple, Optional
import json
import numpy as np

from plagiarism_engine.db import store as default_store

TARGET_DIM = 1024
HAMMING_CANDIDATES = 100


def _row_get(row: Any, key: str, idx: int) -> Any:
    """Read a column from either a dict-like row (RealDictCursor / sqlite3.Row) or a tuple row."""
    if isinstance(row, dict) or hasattr(row, "keys"):
        return row[key]
    return row[idx]


def _calibrate(raw: float, model_name: Optional[str]) -> float:
    from plagiarism_engine.fusion_scorer import calibrate_semantic
    return calibrate_semantic(raw, model_name)


class PgVectorStore:
    def __init__(self, db_store: Optional[Any] = None):
        self.store = db_store if db_store is not None else default_store

    @staticmethod
    def _normalize_and_pad_1d(embedding: np.ndarray, target_dim: int = TARGET_DIM) -> np.ndarray:
        """L2-normalize a 1D float32 embedding and zero-pad (or truncate) to target_dim=1024."""
        vec = np.asarray(embedding, dtype="float32").flatten()
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = vec / norm
        dim = vec.shape[0]
        if dim < target_dim:
            vec = np.pad(vec, (0, target_dim - dim), mode="constant", constant_values=0.0)
        elif dim > target_dim:
            vec = vec[:target_dim]
            norm2 = float(np.linalg.norm(vec))
            if norm2 > 0.0:
                vec = vec / norm2
        return vec

    def _quantize_to_bit_string(self, embedding: np.ndarray) -> str:
        """Convert 1024-dim float32 embedding to a 1024-bit binary string."""
        vec = self._normalize_and_pad_1d(embedding, TARGET_DIM)
        return "".join("1" if x > 0 else "0" for x in vec)

    @staticmethod
    def _parse_embedding(raw: Any) -> Optional[np.ndarray]:
        """Parse an embedding stored as JSON string, pgvector string, or list into a 1D float32 ndarray."""
        if raw is None:
            return None
        if isinstance(raw, np.ndarray):
            return raw.astype("float32").flatten()
        if isinstance(raw, (list, tuple)):
            return np.asarray(raw, dtype="float32").flatten()
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                return None
            try:
                return np.asarray(json.loads(s), dtype="float32").flatten()
            except Exception:
                return None
        return None

    def _make_match(self, source_path: str, domain: str, model: Optional[str],
                    hit_pid: str, hit_path: str, raw_sim: float) -> Dict[str, Any]:
        return {
            "source_file": source_path,
            "matched_project_id": hit_pid,
            "matched_file": hit_path,
            "target_project": hit_pid,
            "target_file": hit_path,
            "similarity": round(_calibrate(raw_sim, model), 4),
            "similarity_raw": round(raw_sim, 4),
            "embedding_model": model,
            "domain": domain,
        }

    # ------------------------------------------------------------------ write

    def store_embeddings_batch(self, project_id: str, batch: List[Tuple]) -> int:
        """
        Store a batch of embeddings using Binary Quantization (BIT(1024) + float32 vector).
        batch: List of (file_id, embedding_ndarray, domain[, model_name]).
        3-tuples are accepted for backward compatibility and are stored with model NULL.
        """
        if not batch:
            return 0

        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            rows = []
            for item in batch:
                file_id, emb = item[0], item[1]
                model_name = item[3] if len(item) > 3 else None
                vec_1024 = self._normalize_and_pad_1d(emb, TARGET_DIM)
                binary_str = "".join("1" if x > 0 else "0" for x in vec_1024)
                emb_str = json.dumps(vec_1024.tolist())
                rows.append((emb_str, binary_str, model_name, file_id))

            if self.store.mode == "postgresql":
                import psycopg2.extras
                psycopg2.extras.execute_batch(
                    cur,
                    "UPDATE project_files SET embedding = %s, embedding_binary = %s::bit(1024), "
                    "embedding_model = %s WHERE id = %s;",
                    rows,
                )
            else:
                cur.executemany(
                    "UPDATE project_files SET embedding = ?, embedding_binary = ?, embedding_model = ? WHERE id = ?;",
                    rows,
                )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    # ----------------------------------------------------------------- search

    def search_bulk(self, project_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Batched 2-Step Rescoring Semantic Search for every embedded file of `project_id`:
        1. Hamming Top-100 candidates per source file on embedding_binary (BIT(1024)),
           restricted to other projects with the same file_type AND the same embedding_model.
        2. Exact float32 cosine rescoring of those candidates; keep top_k per source file.
        """
        if self.store.mode == "postgresql":
            return self._search_bulk_postgres(project_id, top_k)
        return self._search_bulk_sqlite(project_id, top_k)

    def _search_bulk_postgres(self, project_id: str, top_k: int) -> List[Dict[str, Any]]:
        # NOTE: one code path serves both column types. With pgvector the `embedding` column is
        # VECTOR(1024) and `embedding::text` renders as "[...]", which json.loads parses; without
        # pgvector it is TEXT holding the same JSON array. Rescoring happens in NumPy either way.
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT s.id AS source_id, s.relative_path AS source_path, s.file_type AS domain,
                       s.embedding_model AS model, c.id AS cand_id,
                       c.project_id AS cand_pid, c.relative_path AS cand_path
                FROM project_files s
                CROSS JOIN LATERAL (
                    SELECT p.id, p.project_id, p.relative_path
                    FROM project_files p
                    WHERE p.project_id <> s.project_id
                      AND p.file_type = s.file_type
                      AND p.embedding_model IS NOT DISTINCT FROM s.embedding_model
                      AND p.embedding_binary IS NOT NULL
                      AND p.embedding IS NOT NULL
                    ORDER BY bit_count(p.embedding_binary # s.embedding_binary) ASC, p.id ASC
                    LIMIT {HAMMING_CANDIDATES}
                ) c
                WHERE s.project_id = %s
                  AND s.embedding_binary IS NOT NULL
                  AND s.embedding IS NOT NULL;
                """,
                (project_id,),
            )
            pair_rows = cur.fetchall()
            if not pair_rows:
                return []

            sources: Dict[str, Dict[str, Any]] = {}
            needed_ids = set()
            for r in pair_rows:
                sid = _row_get(r, "source_id", 0)
                src = sources.setdefault(sid, {
                    "path": _row_get(r, "source_path", 1),
                    "domain": _row_get(r, "domain", 2),
                    "model": _row_get(r, "model", 3),
                    "cands": [],
                })
                cid = _row_get(r, "cand_id", 4)
                src["cands"].append((cid, _row_get(r, "cand_pid", 5), _row_get(r, "cand_path", 6)))
                needed_ids.add(sid)
                needed_ids.add(cid)

            cur.execute(
                "SELECT id, embedding::text AS embedding FROM project_files WHERE id = ANY(%s);",
                (list(needed_ids),),
            )
            vectors: Dict[str, np.ndarray] = {}
            for r in cur.fetchall():
                parsed = self._parse_embedding(_row_get(r, "embedding", 1))
                if parsed is not None:
                    vectors[_row_get(r, "id", 0)] = self._normalize_and_pad_1d(parsed, TARGET_DIM)
        finally:
            conn.close()

        return self._rescore(sources, vectors, top_k)

    def _search_bulk_sqlite(self, project_id: str, top_k: int) -> List[Dict[str, Any]]:
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, relative_path, file_type, embedding_model, embedding_binary, embedding "
                "FROM project_files WHERE project_id = ? AND embedding_binary IS NOT NULL AND embedding IS NOT NULL;",
                (project_id,),
            )
            source_rows = cur.fetchall()
            if not source_rows:
                return []

            # Load candidates ONCE per (file_type, embedding_model) group, not once per source file.
            groups = {(_row_get(r, "file_type", 2), _row_get(r, "embedding_model", 3)) for r in source_rows}
            group_cands: Dict[Tuple[Any, Any], List[Tuple[str, str, str, int]]] = {}
            vectors: Dict[str, np.ndarray] = {}
            for ftype, model in groups:
                if model is None:
                    cur.execute(
                        "SELECT id, project_id, relative_path, embedding_binary, embedding FROM project_files "
                        "WHERE project_id != ? AND file_type = ? AND embedding_model IS NULL "
                        "AND embedding_binary IS NOT NULL AND embedding IS NOT NULL;",
                        (project_id, ftype),
                    )
                else:
                    cur.execute(
                        "SELECT id, project_id, relative_path, embedding_binary, embedding FROM project_files "
                        "WHERE project_id != ? AND file_type = ? AND embedding_model = ? "
                        "AND embedding_binary IS NOT NULL AND embedding IS NOT NULL;",
                        (project_id, ftype, model),
                    )
                cands = []
                for c in cur.fetchall():
                    cid = _row_get(c, "id", 0)
                    c_bin = _row_get(c, "embedding_binary", 3)
                    parsed = self._parse_embedding(_row_get(c, "embedding", 4))
                    if not c_bin or parsed is None:
                        continue
                    vectors[cid] = self._normalize_and_pad_1d(parsed, TARGET_DIM)
                    cands.append((cid, _row_get(c, "project_id", 1), _row_get(c, "relative_path", 2), int(c_bin, 2)))
                group_cands[(ftype, model)] = cands
        finally:
            conn.close()

        sources: Dict[str, Dict[str, Any]] = {}
        for r in source_rows:
            sid = _row_get(r, "id", 0)
            s_bin = _row_get(r, "embedding_binary", 4)
            parsed = self._parse_embedding(_row_get(r, "embedding", 5))
            if not s_bin or parsed is None:
                continue
            vectors[sid] = self._normalize_and_pad_1d(parsed, TARGET_DIM)
            ftype, model = _row_get(r, "file_type", 2), _row_get(r, "embedding_model", 3)
            src_int = int(s_bin, 2)
            ranked = sorted(group_cands.get((ftype, model), []),
                            key=lambda c: ((src_int ^ c[3]).bit_count(), c[0]))[:HAMMING_CANDIDATES]
            sources[sid] = {
                "path": _row_get(r, "relative_path", 1),
                "domain": ftype,
                "model": model,
                "cands": [(c[0], c[1], c[2]) for c in ranked],
            }

        return self._rescore(sources, vectors, top_k)

    def _rescore(self, sources: Dict[str, Dict[str, Any]], vectors: Dict[str, np.ndarray],
                 top_k: int) -> List[Dict[str, Any]]:
        """Step 2: exact cosine rescoring of each source's Hamming candidates."""
        matches: List[Dict[str, Any]] = []
        for sid, src in sources.items():
            s_vec = vectors.get(sid)
            if s_vec is None:
                continue
            cands = [(cid, pid, path) for cid, pid, path in src["cands"] if cid in vectors]
            if not cands:
                continue
            mat = np.stack([vectors[cid] for cid, _, _ in cands])
            sims = mat @ s_vec
            order = np.argsort(-sims, kind="stable")[:top_k]
            for i in order:
                _, hit_pid, hit_path = cands[int(i)]
                matches.append(self._make_match(src["path"], src["domain"], src["model"],
                                                hit_pid, hit_path, float(sims[int(i)])))
        matches.sort(key=lambda m: m["similarity"], reverse=True)
        return matches

    # ------------------------------------------------------------ maintenance

    def delete_project_embeddings(self, project_id: str) -> int:
        """Clear embedding, embedding_binary and embedding_model for all files in project."""
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            if self.store.mode == "postgresql":
                cur.execute(
                    "UPDATE project_files SET embedding = NULL, embedding_binary = NULL, embedding_model = NULL "
                    "WHERE project_id = %s;",
                    (project_id,),
                )
            else:
                cur.execute(
                    "UPDATE project_files SET embedding = NULL, embedding_binary = NULL, embedding_model = NULL "
                    "WHERE project_id = ?;",
                    (project_id,),
                )
            count = cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def get_pair_similarity(
        self,
        project_a: str,
        path_a: str,
        project_b: str,
        path_b: str,
        raw: bool = False,
    ) -> float:
        """Cosine similarity between two stored files (calibrated by default, raw if raw=True).
        Returns 0.0 if either vector is missing or the two vectors come from different models."""
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            if self.store.mode == "postgresql":
                cur.execute(
                    "SELECT project_id, relative_path, embedding::text AS embedding, embedding_model FROM project_files "
                    "WHERE (project_id = %s AND relative_path = %s) OR (project_id = %s AND relative_path = %s);",
                    (project_a, path_a, project_b, path_b),
                )
            else:
                cur.execute(
                    "SELECT project_id, relative_path, embedding, embedding_model FROM project_files "
                    "WHERE (project_id = ? AND relative_path = ?) OR (project_id = ? AND relative_path = ?);",
                    (project_a, path_a, project_b, path_b),
                )
            rows = cur.fetchall()
            found: Dict[Tuple[str, str], Tuple[np.ndarray, Optional[str]]] = {}
            for r in rows:
                parsed = self._parse_embedding(_row_get(r, "embedding", 2))
                if parsed is not None:
                    key = (_row_get(r, "project_id", 0), _row_get(r, "relative_path", 1))
                    found[key] = (self._normalize_and_pad_1d(parsed, TARGET_DIM), _row_get(r, "embedding_model", 3))
            a = found.get((project_a, path_a))
            b = found.get((project_b, path_b))
            if a is None or b is None:
                return 0.0
            if a[1] != b[1]:
                return 0.0  # different embedding spaces are never comparable
            raw_sim = max(0.0, float(np.dot(a[0], b[0])))
            return round(raw_sim if raw else _calibrate(raw_sim, a[1]), 4)
        except Exception:
            return 0.0
        finally:
            conn.close()

    SKIPPED_MARKER = "skipped:empty"

    def mark_skipped(self, file_ids: List[str]) -> int:
        """Tag files that were intentionally not embedded (empty content) so they are not
        mistaken for an interrupted index run."""
        if not file_ids:
            return 0
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            ph = "%s" if self.store.mode == "postgresql" else "?"
            rows = [(self.SKIPPED_MARKER, fid) for fid in file_ids]
            sql = f"UPDATE project_files SET embedding_model = {ph} WHERE id = {ph} AND embedding_binary IS NULL;"
            if self.store.mode == "postgresql":
                import psycopg2.extras
                psycopg2.extras.execute_batch(cur, sql, rows)
            else:
                cur.executemany(sql, rows)
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def needs_reindex(self, project_id: str, expected_models: Dict[str, Optional[str]]) -> bool:
        """True if the project:
        - has no embedded rows at all, or
        - has any embedded row whose embedding_model differs from expected_models[file_type]
          (legacy untagged rows count as stale), or
        - has rows that are neither embedded nor marked as intentionally skipped
          (an interrupted / partial index run)."""
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            ph = "%s" if self.store.mode == "postgresql" else "?"
            cur.execute(
                f"SELECT file_type, embedding_model, COUNT(*) AS n FROM project_files "
                f"WHERE project_id = {ph} AND embedding_binary IS NOT NULL "
                f"GROUP BY file_type, embedding_model;",
                (project_id,),
            )
            rows = cur.fetchall()
            cur.execute(
                f"SELECT COUNT(*) AS n FROM project_files "
                f"WHERE project_id = {ph} AND embedding_binary IS NULL AND embedding_model IS NULL;",
                (project_id,),
            )
            unindexed = int(_row_get(cur.fetchone(), "n", 0) or 0)
        finally:
            conn.close()
        if not rows:
            return True
        if unindexed > 0:
            return True
        for r in rows:
            ftype = _row_get(r, "file_type", 0) or "text"
            model = _row_get(r, "embedding_model", 1)
            expected = expected_models.get("code" if ftype == "code" else "text")
            if model is None or model != expected:
                return True
        return False

    def count_project_vectors(self, project_id: str) -> int:
        """COUNT(*) WHERE embedding_binary IS NOT NULL"""
        conn = self.store._get_connection()
        try:
            cur = conn.cursor()
            if self.store.mode == "postgresql":
                cur.execute(
                    "SELECT COUNT(*) AS count FROM project_files WHERE project_id = %s AND embedding_binary IS NOT NULL;",
                    (project_id,),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) AS count FROM project_files WHERE project_id = ? AND embedding_binary IS NOT NULL;",
                    (project_id,),
                )
            row = cur.fetchone()
            if not row:
                return 0
            return int(_row_get(row, "count", 0))
        finally:
            conn.close()
