"""Find (and optionally remove) stored files that the file-scope policy now excludes.

Projects uploaded before plagiarism_engine/file_policy.py existed can still contain config,
template, log and data files (package.json, *.yaml, android_build_log.txt, train.csv, ...).
The engine already ignores them at scan time; this script cleans them out of the database.

    python scripts/purge_excluded_files.py                 # DRY RUN (default): report only, no changes
    python scripts/purge_excluded_files.py --project X     # dry run for one project
    python scripts/purge_excluded_files.py --apply         # delete rows + fingerprints + stored copies

--apply removes, per excluded file: its project_files row (content + vectors), its fingerprint_index
rows, and its stored copy in the StorageService. Authored source/text files are never touched.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plagiarism_engine.db import store  # noqa: E402
from plagiarism_engine.file_policy import is_scannable  # noqa: E402


def _rows(cur):
    out = []
    for r in cur.fetchall():
        out.append(tuple(r[k] for k in r.keys()) if hasattr(r, "keys") else tuple(r))
    return out


def find_excluded(project: str = None):
    ph = "%s" if store.mode == "postgresql" else "?"
    conn = store._get_connection()
    try:
        cur = conn.cursor()
        sql = ("SELECT project_id, relative_path, (embedding_binary IS NOT NULL) AS embedded "
               "FROM project_files")
        params = ()
        if project:
            sql += f" WHERE project_id = {ph}"
            params = (project,)
        cur.execute(sql + ";", params)
        files = _rows(cur)

        cur.execute("SELECT project_id, file_path, COUNT(*) FROM fingerprint_index GROUP BY project_id, file_path;")
        fp_counts = {(p, f): int(n) for p, f, n in _rows(cur)}
    finally:
        conn.close()

    excluded = []
    for pid, path, embedded in files:
        ok, reason = is_scannable(path)
        if not ok:
            excluded.append({
                "project_id": pid, "path": path, "reason": reason,
                "embedded": bool(embedded), "fingerprints": fp_counts.get((pid, path), 0),
            })
    return excluded, len(files)


def apply_purge(excluded):
    from plagiarism_engine.storage import get_storage_service
    storage = get_storage_service()
    ph = "%s" if store.mode == "postgresql" else "?"
    conn = store._get_connection()
    try:
        cur = conn.cursor()
        for item in excluded:
            pid, path = item["project_id"], item["path"]
            cur.execute(f"DELETE FROM fingerprint_index WHERE project_id = {ph} AND file_path = {ph};", (pid, path))
            cur.execute(f"DELETE FROM project_files WHERE project_id = {ph} AND relative_path = {ph};", (pid, path))
        conn.commit()
    finally:
        conn.close()
    removed_copies = 0
    for item in excluded:
        try:
            storage.delete_file(f"{item['project_id']}/{item['path']}")
            removed_copies += 1
        except Exception:
            pass
    return removed_copies


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="limit to one project id")
    ap.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    ap.add_argument("--json", help="also write the full list to this JSON file")
    args = ap.parse_args()

    excluded, total = find_excluded(args.project)
    by_project = defaultdict(list)
    for item in excluded:
        by_project[item["project_id"]].append(item)

    mode = "APPLY" if args.apply else "DRY RUN (no changes)"
    print(f"[purge] mode: {mode} | DB: {store.mode} | stored files scanned: {total} | excluded: {len(excluded)}")
    print(f"[purge] by reason: {dict(Counter(i['reason'] for i in excluded))}")
    for pid in sorted(by_project):
        items = by_project[pid]
        fps = sum(i["fingerprints"] for i in items)
        emb = sum(i["embedded"] for i in items)
        print(f"\n  {pid}: {len(items)} file(s), {fps} fingerprint(s), {emb} embedded")
        for i in sorted(items, key=lambda x: x["path"])[:25]:
            print(f"    - [{i['reason']}] {i['path']}  (fps={i['fingerprints']}, embedded={i['embedded']})")
        if len(items) > 25:
            print(f"    ... and {len(items) - 25} more")

    if args.json:
        Path(args.json).write_text(json.dumps(excluded, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\n[purge] full list written to {args.json}")

    if args.apply and excluded:
        copies = apply_purge(excluded)
        print(f"\n[purge] deleted {len(excluded)} file row(s) and their fingerprints; removed {copies} stored copies.")
    elif not args.apply:
        print("\n[purge] dry run only. Re-run with --apply to delete.")


if __name__ == "__main__":
    main()
