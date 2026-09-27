"""
Perf probe for the decoupled upload stream (backend.py::_run_intake).

Verifies that POST /api/plagiarism/upload-scan-stream (and the ZIP variant)
no longer runs CodeBERT / BGE-M3 embedding + FAISS indexing, while Winnowing
fingerprinting stays fully active.

Run with the backend interpreter:
    & 'D:\\AI engine\\.venv\\Scripts\\python.exe' verify_upload_perf.py
"""
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests
from jose import jwt

BASE = os.environ.get("PERF_BASE_URL", "http://127.0.0.1:8000")
JWT_SECRET = os.environ.get(
    "JWT_SECRET", "ministry-plagiarism-secret-key-change-in-production"
)
SKIP_MSG = "[PHASE 2/3] Skipping Deep Semantic Indexing (Deferred to Deep Scan mode)..."
N_CODE = int(os.environ.get("PERF_CODE_FILES", "25"))
N_TEXT = int(os.environ.get("PERF_TEXT_FILES", "3"))
PROJECT = os.environ.get("PERF_PROJECT", f"perf_probe_{int(time.time())}")
FAISS_MARKERS = ("[FAISS]", "Encoding ", "Vector indexing", "embeddings")

HERE = os.path.dirname(os.path.abspath(__file__))


def mint_token() -> str:
    """require_role() only validates the JWT signature, so mint one locally."""
    payload = {
        "user_id": "perf-probe",
        "email": "perf@probe.local",
        "role": "ministry_admin",
        "requires_password_change": False,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def code_file(idx: int) -> str:
    lines = [
        f'"""Synthetic module {idx} generated for upload perf probing."""',
        "",
        "import math",
        "import hashlib",
        "",
    ]
    for fn in range(14):
        lines += [
            f"def process_batch_{idx}_{fn}(records, threshold={fn + 1}):",
            f'    """Aggregate batch {fn} of module {idx}."""',
            "    totals = {}",
            "    for record in records:",
            "        digest = hashlib.sha256(",
            f"            f'{{record}}::{idx}_{fn}'.encode()",
            "        ).hexdigest()[:16]",
            "        value = 0",
            "        for offset in range(len(record)):",
            f"            value += (ord(record[offset]) * (offset + {fn + 1})) % 97",
            "        if value > threshold:",
            "            totals[digest] = math.sqrt(value)",
            "        else:",
            "            totals[digest] = value / 2.0",
            "    return totals",
            "",
        ]
    return "\n".join(lines)


def text_file(idx: int) -> str:
    paragraphs = []
    for p in range(24):
        paragraphs.append(" ".join([
            f"Section {p} of document {idx} discusses the sampling protocol.",
            f"The cohort {idx}-{p} was measured twice with calibrated instruments.",
            f"Results for batch {p} were normalised against reference curve {idx}.",
            "Any deviation above the tolerated margin is reported to the supervisor.",
        ]))
    return "\n\n".join(paragraphs)


def build_corpus(n_code: int = N_CODE, n_text: int = N_TEXT):
    """File records shaped exactly like FileExtractor output."""
    files = []
    for i in range(n_code):
        files.append({
            "relative_path": f"src/module_{i:02d}.py",
            "filename": f"module_{i:02d}.py",
            "extension": ".py",
            "file_type": "code",
            "content": code_file(i),
        })
    for i in range(n_text):
        files.append({
            "relative_path": f"docs/report_{i:02d}.txt",
            "filename": f"report_{i:02d}.txt",
            "extension": ".txt",
            "file_type": "text",
            "content": text_file(i),
        })
    return files


def stream_upload(url, headers, data, files, label):
    """POST a multipart upload and consume the SSE stream, timing every event."""
    print(f"\n=== {label}  ->  {url}")
    events = []
    t0 = time.time()
    with requests.post(
        url, headers=headers, data=data, files=files, stream=True, timeout=1800
    ) as res:
        if res.status_code != 200:
            print(f"  HTTP {res.status_code}: {res.text[:400]}")
            return time.time() - t0, events
        for raw in res.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore")
            if not line.startswith("data: "):
                continue
            evt = json.loads(line[6:])
            elapsed = time.time() - t0
            events.append((elapsed, evt))
            text = evt.get("text") or json.dumps(evt, default=str)[:200]
            print(f"  [{elapsed:7.2f}s] {text}")
            if evt.get("type") in ("complete", "error"):
                break
    return time.time() - t0, events


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'} :: {name}{(' -> ' + detail) if detail else ''}")
    return ok


def main() -> int:
    token = mint_token()
    headers = {"Authorization": f"Bearer {token}"}
    corpus = build_corpus()
    total_loc = sum(
        len([ln for ln in f["content"].splitlines() if ln.strip()]) for f in corpus
    )
    print(f"Corpus: {len(corpus)} files / {total_loc} LOC -> project '{PROJECT}'")

    for _ in range(30):
        try:
            health = requests.get(f"{BASE}/api/system/health", timeout=5).json()
            print(f"Server health: {health}")
            break
        except Exception:
            time.sleep(2)
    else:
        print("Server never became reachable.")
        return 1

    results = []

    # --- 1. multipart upload + scan (SSE) ---
    payload = [
        ("files", (f["relative_path"], io.BytesIO(f["content"].encode("utf-8")),
                   "application/octet-stream"))
        for f in corpus
    ]
    t_direct, ev_direct = stream_upload(
        f"{BASE}/api/plagiarism/upload-scan-stream",
        headers,
        {"project_name": PROJECT, "scan_type": "Direct Upload Project Scan"},
        payload,
        "upload-scan-stream",
    )

    # --- 2. ZIP archive upload + scan (SSE, same _run_intake path) ---
    zip_project = f"{PROJECT}_zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in corpus:
            zf.writestr(f["relative_path"], f["content"])
    buf.seek(0)
    t_zip, ev_zip = stream_upload(
        f"{BASE}/api/plagiarism/upload-zip-stream",
        headers,
        {"project_name": zip_project, "scan_type": "ZIP Archive Scan"},
        [("file", ("project.zip", buf, "application/zip"))],
        "upload-zip-stream",
    )

    print("\n--- ASSERTIONS ---")
    for label, total, events in (
        ("upload-scan-stream", t_direct, ev_direct),
        ("upload-zip-stream", t_zip, ev_zip),
    ):
        texts = [e.get("text", "") for _, e in events]
        joined = "\n".join(texts)
        fp = re.search(r"(\d+) fingerprints computed in ([\d.]+)s", joined)
        results.append(check(
            f"{label}: stream completed", any(e.get("type") == "complete" for _, e in events)))
        results.append(check(f"{label}: skip message emitted", any(SKIP_MSG in t for t in texts)))
        leaked = [t for t in texts if any(m in t for m in FAISS_MARKERS)]
        results.append(check(f"{label}: no FAISS/embedding work", not leaked, str(leaked[:2])))
        results.append(check(
            f"{label}: Winnowing fingerprints intact",
            bool(fp) and int(fp.group(1)) > 0,
            f"{fp.group(1) if fp else 0} fingerprints",
        ))
        results.append(check(
            f"{label}: finished in seconds ({total:.2f}s < 60s)", total < 60.0))

    idx_dir = os.path.join(HERE, "data", "faiss_index")
    mapping = os.path.join(HERE, "data", "faiss_mapping.json")
    artifacts = sorted(os.listdir(idx_dir)) if os.path.isdir(idx_dir) else []
    print(f"\ndata/faiss_index contents : {artifacts or '(empty)'}")
    print(f"data/faiss_mapping.json   : exists={os.path.exists(mapping)}")
    if os.path.exists(mapping):
        blob = open(mapping, encoding="utf-8").read()
        results.append(check(
            "FAISS mapping untouched by upload", PROJECT not in blob))

    for pid in (PROJECT, zip_project):
        r = requests.delete(f"{BASE}/api/plagiarism/projects/{pid}", headers=headers, timeout=60)
        print(f"cleanup DELETE {pid}: HTTP {r.status_code}")

    print(f"\nRESULT: {sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

