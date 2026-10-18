"""
Real-corpus evaluation harness: ingest real project folders through the engine's own pipeline,
then run Quick Scan (Winnowing + hybrid fusion) and Deep Scan (bulk semantic search) on each.

All source folders are opened READ-ONLY (FileExtractor.scan_project_directory only reads files).
Projects are stored in the engine DB under ids prefixed `realeval_` so they are easy to find in the
UI and to remove later (`--phase cleanup`).

Phases (run in order, each persists JSON under real_corpus_eval/):
  size     - dry run: what the engine would ingest per folder (no DB writes)
  ingest   - _run_intake (DB save + Winnowing fingerprints)            == upload step
  quick    - _run_analysis per project (lexical + fusion; auto-indexes embeddings)  == Quick Scan
  deep     - VectorStore.search_bulk per project                       == Deep Scan (bulk)
  report   - write REAL_CORPUS_EVAL.md from the JSON results
  cleanup  - delete every realeval_* project from the DB

Usage:
  python scripts/real_corpus_eval.py --phase size
  python scripts/real_corpus_eval.py --phase ingest [--only mizan_monorepo,accounting]
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

from plagiarism_engine.config import load_project_env  # noqa: E402

load_project_env()

FOLDERS = [
    r"D:\mizan_monorepo",
    r"D:\3d-react-website",
    r"D:\accounting",
    r"D:\AI engine",
    r"D:\AI surveillance system",
    r"D:\application of TinyML",
    r"D:\C# accounting app(Mizan)",
    r"D:\Compressed",
    r"D:\crystal-helix-erp",
    r"D:\CyberSecurity+DIP projects",
    r"D:\Encrypted Traffic analysis",
    r"D:\frontend",
    r"D:\local-agent-ui-ready",
    r"D:\LordsMobileBot",
    r"D:\manus-like agent",
]

OUT_DIR = PROJECT_ROOT / "real_corpus_eval"
PREFIX = "realeval_"

# Per-folder extra ignore dirs, on top of the engine's DEFAULT_IGNORE_DIRS.
# manus-like agent/repos holds ~5,350 files of cloned third-party repositories (gemini-cli, opencode,
# claw-code, incl. a 56 MB JSON test fixture) - not the author's own code.
EXTRA_IGNORE_DIRS = {
    "manus_like_agent": {"repos"},
}


def extract_folder(folder: str):
    """Run the engine's own directory extractor, adding any per-folder extra ignore dirs."""
    from plagiarism_engine.extractor import FileExtractor, DEFAULT_IGNORE_DIRS

    extra = EXTRA_IGNORE_DIRS.get(slug(folder)[len(PREFIX):])
    ignore = (set(DEFAULT_IGNORE_DIRS) | extra) if extra else None
    return FileExtractor.scan_project_directory(folder, ignore_dirs=ignore)


def slug(folder: str) -> str:
    name = Path(folder).name
    return PREFIX + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def save_json(name: str, data) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(name: str, default=None):
    p = OUT_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def selected(only: str):
    if not only:
        return FOLDERS
    wanted = {w.strip().lower() for w in only.split(",") if w.strip()}
    return [f for f in FOLDERS if slug(f)[len(PREFIX):] in wanted or Path(f).name.lower() in wanted]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# --------------------------------------------------------------------------- size

def phase_size(folders):
    results = load_json("size.json", {}) or {}
    for folder in folders:
        pid = slug(folder)
        if not Path(folder).is_dir():
            results[pid] = {"folder": folder, "error": "folder not found"}
            log(f"[size] {folder}: NOT FOUND")
            continue
        t0 = time.perf_counter()
        try:
            files = extract_folder(folder)
        except Exception as e:
            results[pid] = {"folder": folder, "error": str(e)}
            log(f"[size] {folder}: ERROR {e}")
            continue
        dt = time.perf_counter() - t0
        by_type = Counter(f.get("file_type", "?") for f in files)
        by_ext = Counter(Path(f.get("relative_path", "")).suffix.lower() or "(none)" for f in files)
        chars = sum(len(f.get("content", "")) for f in files)
        largest = sorted(((len(f.get("content", "")), f.get("relative_path", "")) for f in files), reverse=True)[:8]
        top_dirs = Counter(Path(f.get("relative_path", "")).parts[0] if Path(f.get("relative_path", "")).parts else "" for f in files)
        results[pid] = {
            "folder": folder,
            "files": len(files),
            "code_files": by_type.get("code", 0),
            "text_files": by_type.get("text", 0),
            "total_chars": chars,
            "scan_seconds": round(dt, 1),
            "top_extensions": by_ext.most_common(10),
            "top_level_dirs": top_dirs.most_common(8),
            "largest_files": [{"chars": c, "path": p} for c, p in largest],
        }
        log(f"[size] {pid}: {len(files)} files ({by_type.get('code', 0)} code / {by_type.get('text', 0)} text), "
            f"{chars / 1e6:.1f}M chars, scanned in {dt:.1f}s")
        save_json("size.json", results)
    return results


# ------------------------------------------------------------------------- ingest

def phase_ingest(folders):
    from app.services.intake import _run_intake

    results = load_json("ingest.json", {}) or {}
    for folder in folders:
        pid = slug(folder)
        if not Path(folder).is_dir():
            continue
        t0 = time.perf_counter()
        files = extract_folder(folder)
        if not files:
            results[pid] = {"folder": folder, "files": 0, "skipped": "no ingestible source/text files"}
            log(f"[ingest] {pid}: skipped (0 ingestible files)")
            save_json("ingest.json", results)
            continue
        for f in files:
            f.setdefault("relative_path", f.get("filename", ""))
        t1 = time.perf_counter()
        res = _run_intake(pid, files, log_callback=lambda m, p=pid: log(f"[ingest:{p}] {m}"))
        t2 = time.perf_counter()
        results[pid] = {
            "folder": folder,
            "files": res.get("total_files"),
            "code_files": res.get("code_files_count"),
            "text_files": res.get("text_files_count"),
            "loc": res.get("total_loc"),
            "extract_seconds": round(t1 - t0, 1),
            "intake_seconds": round(t2 - t1, 1),
        }
        log(f"[ingest] {pid}: {results[pid]}")
        save_json("ingest.json", results)
    return results


# --------------------------------------------------------------------- embeddings

def phase_embed(folders):
    """Pre-build semantic vectors for every realeval project (timed separately from the scans)."""
    from app.state import get_db, get_vstore
    from app.services.embeddings import _index_project_embeddings

    db, vs = get_db(), get_vstore()
    results = load_json("embed.json", {}) or {}
    for folder in folders:
        pid = slug(folder)
        if not db.get_project_by_id(pid):
            continue
        if not vs.needs_reindex(pid) and pid in results:
            log(f"[embed] {pid}: up to date")
            continue
        t0 = time.perf_counter()
        try:
            added = _index_project_embeddings(vs, db, pid, log_callback=lambda m, p=pid: log(f"[embed:{p}] {m}"))
            err = None
        except Exception as e:
            added, err = {}, str(e)
        results[pid] = {"vectors": added, "seconds": round(time.perf_counter() - t0, 1), "error": err}
        log(f"[embed] {pid}: {results[pid]}")
        save_json("embed.json", results)
    return results


# -------------------------------------------------------------------------- quick

def phase_quick(folders):
    from app.services.intake import _run_analysis

    results = load_json("quick.json", {}) or {}
    for folder in folders:
        pid = slug(folder)
        t0 = time.perf_counter()
        try:
            res = _run_analysis(pid, log_callback=lambda m, p=pid: log(f"[quick:{p}] {m}"))
        except Exception as e:
            results[pid] = {"error": str(e)}
            log(f"[quick] {pid}: ERROR {e}")
            save_json("quick.json", results)
            continue
        dt = time.perf_counter() - t0
        comps = res.get("comparisons", [])
        results[pid] = {
            "seconds": round(dt, 1),
            "overall_similarity": res.get("overall_similarity"),
            "verdict": res.get("verdict"),
            "n_comparisons": len(comps),
            "comparisons": [
                {k: c.get(k) for k in ("project", "file1", "file2", "type", "winnowing_score", "semantic_score",
                                       "fusion_score", "containment_score", "embedded_copy", "alpha", "status")}
                for c in comps
            ],
        }
        log(f"[quick] {pid}: {len(comps)} comparisons, overall={res.get('overall_similarity')} "
            f"verdict={res.get('verdict')} in {dt:.1f}s")
        save_json("quick.json", results)
    return results


# --------------------------------------------------------------------------- deep

def phase_deep(folders):
    from app.state import get_vstore

    vs = get_vstore()
    results = load_json("deep.json", {}) or {}
    for folder in folders:
        pid = slug(folder)
        t0 = time.perf_counter()
        try:
            matches = vs.search_bulk(pid, top_k=5)
        except Exception as e:
            results[pid] = {"error": str(e)}
            save_json("deep.json", results)
            continue
        dt = time.perf_counter() - t0
        results[pid] = {
            "seconds": round(dt, 2),
            "n_matches": len(matches),
            "matches": [{k: m.get(k) for k in ("source_file", "matched_project_id", "matched_file", "similarity",
                                                "similarity_raw", "embedding_model", "domain")} for m in matches],
        }
        log(f"[deep] {pid}: {len(matches)} matches in {dt:.2f}s")
        save_json("deep.json", results)
    return results


# ------------------------------------------------------------------------- report

def _pair_matrix(results, score_key, project_key):
    """max score per (source project, target project) from a results dict."""
    mat = defaultdict(dict)
    for src, data in (results or {}).items():
        for row in data.get("comparisons", data.get("matches", [])) or []:
            tgt = row.get(project_key)
            if not tgt:
                continue
            try:
                val = float(row.get(score_key) or 0)
            except (TypeError, ValueError):
                continue
            if score_key == "similarity":
                val *= 100.0
            mat[src][tgt] = max(mat[src].get(tgt, 0.0), val)
    return mat


def phase_report(folders):
    size = load_json("size.json", {}) or {}
    ingest = load_json("ingest.json", {}) or {}
    embed = load_json("embed.json", {}) or {}
    quick = load_json("quick.json", {}) or {}
    deep = load_json("deep.json", {}) or {}
    pids = [slug(f) for f in folders]
    short = {p: p[len(PREFIX):][:22] for p in pids}

    lines = ["# Real-Corpus Evaluation — Quick Scan vs Deep Scan", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `scripts/real_corpus_eval.py`. "
             "Source folders were read-only; projects are stored with the `realeval_` prefix.", "",
             "## 1. Corpus", "",
             "| Project | Folder | Files | Code | Text | Chars | Ingest s | Embed s | Vectors (code/text) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for p in pids:
        s, i, e = size.get(p, {}), ingest.get(p, {}), embed.get(p, {})
        vec = e.get("vectors") or {}
        lines.append(f"| `{short[p]}` | `{s.get('folder', '')}` | {i.get('files', s.get('files', '-'))} | "
                     f"{i.get('code_files', s.get('code_files', '-'))} | {i.get('text_files', s.get('text_files', '-'))} | "
                     f"{s.get('total_chars', '-')} | {i.get('intake_seconds', '-')} | {e.get('seconds', '-')} | "
                     f"{vec.get('code', '-')}/{vec.get('text', '-')} |")

    for title, mat in (("2. Quick Scan — max fusion score (%) per project pair",
                        _pair_matrix(quick, "fusion_score", "project")),
                       ("3. Deep Scan — max calibrated semantic similarity (%) per project pair",
                        _pair_matrix(deep, "similarity", "matched_project_id"))):
        lines += ["", f"## {title}", "", "Rows = scanned project, columns = matched project. Blank = no match reported.", "",
                  "| ↓ scanned / matched → | " + " | ".join(f"`{short[p][:10]}`" for p in pids) + " |",
                  "|---|" + "---|" * len(pids)]
        for src in pids:
            cells = []
            for tgt in pids:
                v = mat.get(src, {}).get(tgt)
                cells.append("—" if src == tgt else (f"{v:.0f}" if v is not None else ""))
            lines.append(f"| `{short[src]}` | " + " | ".join(cells) + " |")

    lines += ["", "## 4. Per-project scan summary", "",
              "| Project | Quick s | Quick verdict | Quick overall % | # comparisons | Deep s | # deep matches |",
              "|---|---|---|---|---|---|---|"]
    for p in pids:
        q, d = quick.get(p, {}), deep.get(p, {})
        lines.append(f"| `{short[p]}` | {q.get('seconds', '-')} | {q.get('verdict', q.get('error', '-'))} | "
                     f"{q.get('overall_similarity', '-')} | {q.get('n_comparisons', '-')} | {d.get('seconds', '-')} | "
                     f"{d.get('n_matches', '-')} |")

    lines += ["", "## 5. Top 25 file-level matches (Quick Scan, by fusion score)", "",
              "| Scanned project | File | Matched project | Matched file | Win % | Sem % | Fusion % | Contain % | Verdict |",
              "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for src, data in quick.items():
        for c in data.get("comparisons", []) or []:
            rows.append((float(c.get("fusion_score") or 0), src, c))
    for score, src, c in sorted(rows, key=lambda r: r[0], reverse=True)[:25]:
        lines.append(f"| `{short.get(src, src)}` | `{c.get('file1')}` | `{str(c.get('project', ''))[len(PREFIX):][:22]}` | "
                     f"`{c.get('file2')}` | {c.get('winnowing_score')} | {c.get('semantic_score')} | {score} | "
                     f"{c.get('containment_score')} | {c.get('status')} |")

    out = PROJECT_ROOT / "REAL_CORPUS_EVAL.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"[report] wrote {out}")


# ------------------------------------------------------------------------ cleanup

def phase_cleanup(_folders):
    from app.state import get_db

    db = get_db()
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        ph = "%s" if db.mode == "postgresql" else "?"
        cur.execute(f"SELECT id FROM projects WHERE id LIKE {ph};", (PREFIX + "%",))
        ids = [r[0] if not hasattr(r, "keys") else r["id"] for r in cur.fetchall()]
    finally:
        conn.close()
    for pid in ids:
        db.delete_project(pid)
        log(f"[cleanup] deleted {pid}")


PHASES = {"size": phase_size, "ingest": phase_ingest, "embed": phase_embed, "quick": phase_quick,
          "deep": phase_deep, "report": phase_report, "cleanup": phase_cleanup}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=list(PHASES))
    ap.add_argument("--only", default="", help="comma-separated folder names / slugs")
    args = ap.parse_args()
    PHASES[args.phase](selected(args.only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
