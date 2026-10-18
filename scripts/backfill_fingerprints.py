"""
Backfill Winnowing fingerprints for stored projects (maintenance script).

Needed once after the Winnowing dead-zone fix: files with k <= tokens < k + w - 1 previously
produced ZERO fingerprints, so they were never stored in `fingerprint_index` and could never be
found as lexical candidates. This recomputes fingerprints from the stored file contents and
inserts them additively (ON CONFLICT DO NOTHING) - existing fingerprints, file rows and
embeddings are not modified.

Usage:
  python scripts/backfill_fingerprints.py                 # all projects
  python scripts/backfill_fingerprints.py --prefix realeval_
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plagiarism_engine.config import load_project_env  # noqa: E402

load_project_env()

from plagiarism_engine.db import SystemDBStore  # noqa: E402
from plagiarism_engine.winnowing import WinnowingEngine  # noqa: E402


def project_ids(db, prefix: str):
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        if prefix:
            ph = "%s" if db.mode == "postgresql" else "?"
            cur.execute(f"SELECT id FROM projects WHERE id LIKE {ph} ORDER BY id;", (prefix + "%",))
        else:
            cur.execute("SELECT id FROM projects ORDER BY id;")
        return [r[0] if not hasattr(r, "keys") else r["id"] for r in cur.fetchall()]
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="", help="only projects whose id starts with this prefix")
    args = ap.parse_args()

    db = SystemDBStore()
    winnow = WinnowingEngine()
    for pid in project_ids(db, args.prefix):
        t0 = time.perf_counter()
        files = db.get_project_files(pid)
        batch, total = [], 0
        for f in files:
            content = f.get("content", "") or ""
            rel = f.get("relative_path", "")
            ftype = f.get("file_type", "")
            if not content.strip():
                continue
            if ftype == "code":
                fps = winnow.compute_code_fingerprints(content, rel)
            elif ftype == "text":
                fps = winnow.compute_text_fingerprints(content)
            else:
                continue
            if fps:
                batch.append((rel, ftype, fps))
                total += len(fps)
        db.store_fingerprints_batch(pid, batch)
        print(f"[backfill] {pid}: {len(files)} files, {total} fingerprints (re)submitted in "
              f"{time.perf_counter() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
