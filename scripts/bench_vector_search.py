"""
Vector search benchmark (Round 2 - Task T10).

Compares the round-1 search algorithm ("old": one Hamming Top-100 SQL query per source file,
each returning the candidates' full JSON embeddings) against the round-2 batched algorithm
("new": PgVectorStore.search_bulk -> one LATERAL query for candidate ids, then each distinct
embedding fetched once and rescored in NumPy).

- Inserts synthetic 768-d L2-normalized vectors (zero-padded to 1024 like the pipeline):
  default 50 projects x 100 files = 5,000 rows, project ids prefixed `bench_r2_<tag>_`.
  File j of every project is a noisy copy of a shared base vector j, so there are real
  near-duplicate neighbours to find.
- Times search_bulk for one 100-file project: 5 runs each, reports the median.
- Reports the top-5 agreement between old and new (same top-5 set per source file).
- Deletes every bench project at the end, including on error.

PostgreSQL only (the live path on this machine: PostgreSQL without pgvector).
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plagiarism_engine.config import load_project_env  # noqa: E402

load_project_env()

from plagiarism_engine.db import SystemDBStore  # noqa: E402
from plagiarism_engine.vectors.pgvector_store import PgVectorStore, TARGET_DIM  # noqa: E402

BENCH_MODEL = "bench-synthetic-768"


def _row(r, key, idx):
    return r[key] if (isinstance(r, dict) or hasattr(r, "keys")) else r[idx]


def old_search_bulk(db, store: PgVectorStore, project_id: str, top_k: int = 5):
    """Faithful port of the round-1 PostgreSQL (no pgvector) branch of PgVectorStore.search_bulk."""
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT relative_path, file_type, embedding_binary::text AS embedding_binary, embedding::text AS embedding "
            "FROM project_files WHERE project_id = %s AND embedding_binary IS NOT NULL;",
            (project_id,),
        )
        source_files = cur.fetchall()
        matches = []
        for row in source_files:
            source_path = _row(row, "relative_path", 0)
            source_domain = _row(row, "file_type", 1)
            source_bin = _row(row, "embedding_binary", 2)
            source_emb_raw = _row(row, "embedding", 3)
            cur.execute(
                """
                SELECT project_id, relative_path, embedding::text AS embedding
                FROM project_files
                WHERE project_id != %s
                  AND file_type = %s
                  AND embedding_binary IS NOT NULL
                  AND embedding IS NOT NULL
                ORDER BY bit_count(embedding_binary # %s::bit(1024)) ASC
                LIMIT 100;
                """,
                (project_id, source_domain, source_bin),
            )
            candidates = cur.fetchall()
            source_vec = store._parse_embedding(source_emb_raw)
            if source_vec is None:
                continue
            source_vec = store._normalize_and_pad_1d(source_vec, TARGET_DIM)
            scored = []
            for cand in candidates:
                cand_vec = store._parse_embedding(_row(cand, "embedding", 2))
                if cand_vec is None:
                    continue
                cand_vec = store._normalize_and_pad_1d(cand_vec, TARGET_DIM)
                scored.append((_row(cand, "project_id", 0), _row(cand, "relative_path", 1), float(np.dot(source_vec, cand_vec))))
            scored.sort(key=lambda x: x[2], reverse=True)
            for pid, path, sim in scored[:top_k]:
                matches.append({"source_file": source_path, "matched_project_id": pid, "matched_file": path, "similarity": sim})
        return matches
    finally:
        conn.close()


def top5_sets(matches):
    out = {}
    for m in matches:
        out.setdefault(m["source_file"], set()).add((m["matched_project_id"], m["matched_file"]))
    return out


def seed(db, prefix: str, n_projects: int, n_files: int, rng) -> list:
    import psycopg2.extras

    store = PgVectorStore(db_store=db)
    base = rng.standard_normal((n_files, 768)).astype("float32")
    project_ids = [f"{prefix}{p:03d}" for p in range(n_projects)]
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_batch(
            cur, "INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;",
            [(pid, pid) for pid in project_ids],
        )
        rows = []
        for pid in project_ids:
            noise_scale = float(rng.uniform(0.3, 1.2))
            for j in range(n_files):
                v = base[j] + noise_scale * rng.standard_normal(768).astype("float32")
                vec = store._normalize_and_pad_1d(v, TARGET_DIM)
                bits = "".join("1" if x > 0 else "0" for x in vec)
                rows.append((f"{pid}::src/file_{j:03d}.py", pid, f"src/file_{j:03d}.py", "code", "",
                             json.dumps(vec.tolist()), bits, BENCH_MODEL))
        psycopg2.extras.execute_batch(
            cur,
            "INSERT INTO project_files (id, project_id, relative_path, file_type, content, embedding, "
            "embedding_binary, embedding_model) VALUES (%s, %s, %s, %s, %s, %s, %s::bit(1024), %s);",
            rows, page_size=500,
        )
        conn.commit()
    finally:
        conn.close()
    return project_ids


def cleanup(db, prefix: str) -> None:
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM project_files WHERE project_id LIKE %s;", (prefix + "%",))
        cur.execute("DELETE FROM projects WHERE id LIKE %s;", (prefix + "%",))
        conn.commit()
    finally:
        conn.close()


def time_runs(fn, runs: int):
    times, result = [], None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), times, result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", type=int, default=50)
    ap.add_argument("--files", type=int, default=100)
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    db = SystemDBStore()
    if db.mode != "postgresql":
        print("[bench] PostgreSQL is not active; benchmark requires the live PostgreSQL path.")
        return 1

    prefix = f"bench_r2_{uuid.uuid4().hex[:6]}_"
    rng = np.random.default_rng(2026)
    store = PgVectorStore(db_store=db)
    try:
        t0 = time.perf_counter()
        project_ids = seed(db, prefix, args.projects, args.files, rng)
        total_rows = args.projects * args.files
        print(f"[bench] Seeded {total_rows} rows across {args.projects} projects in {time.perf_counter() - t0:.1f}s "
              f"(has_pgvector={db.has_pgvector})")
        target = project_ids[0]

        # Warm-up (connection pool, plan cache) for both, not timed.
        old_search_bulk(db, store, target, 5)
        store.search_bulk(target, 5)

        old_med, old_times, old_res = time_runs(lambda: old_search_bulk(db, store, target, 5), args.runs)
        new_med, new_times, new_res = time_runs(lambda: store.search_bulk(target, 5), args.runs)

        old_sets, new_sets = top5_sets(old_res), top5_sets(new_res)
        sources = sorted(set(old_sets) | set(new_sets))
        agree = sum(1 for s in sources if old_sets.get(s) == new_sets.get(s))
        pct = 100.0 * agree / len(sources) if sources else 0.0

        print(f"[bench] Rows in table for benchmark: {total_rows} (+ any pre-existing rows)")
        print(f"[bench] Query project: {args.files} source files, top_k=5, Hamming candidates=100")
        print(f"[bench] OLD (per-file queries) median: {old_med * 1000:.1f} ms  runs={[round(t * 1000, 1) for t in old_times]}")
        print(f"[bench] NEW (batched LATERAL)  median: {new_med * 1000:.1f} ms  runs={[round(t * 1000, 1) for t in new_times]}")
        print(f"[bench] Speed-up: {old_med / new_med:.2f}x")
        print(f"[bench] Top-5 agreement: {agree}/{len(sources)} source files = {pct:.1f}%")
        return 0 if pct >= 95.0 else 2
    finally:
        cleanup(db, prefix)
        print(f"[bench] Cleaned up all '{prefix}*' projects.")


if __name__ == "__main__":
    sys.exit(main())
