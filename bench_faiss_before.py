"""
Baseline benchmark: cost of the FAISS/CodeBERT/BGE-M3 indexing step that was
removed from the upload stream (backend.py::_run_intake).

Runs against a THROWAWAY index dir so data/faiss_index is never touched.

    & 'D:\\AI engine\\.venv\\Scripts\\python.exe' bench_faiss_before.py
"""
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("MODELS_DIR", r"D:\AI engine\models")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Engine log lines contain emoji; redirected stdout defaults to cp1252 on Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from verify_upload_perf import build_corpus  # noqa: E402

N_CODE = int(os.environ.get("BENCH_CODE_FILES", "10"))
N_TEXT = int(os.environ.get("BENCH_TEXT_FILES", "2"))


def main() -> int:
    from plagiarism_engine.vector_store import VectorStore, model_pool

    corpus = build_corpus(N_CODE, N_TEXT)
    chars = sum(len(f["content"]) for f in corpus)
    print(f"Corpus: {len(corpus)} files ({N_CODE} code + {N_TEXT} text), {chars:,} chars")

    t0 = time.time()
    model_pool.get_model("code")
    t_code_model = time.time() - t0
    t0 = time.time()
    model_pool.get_model("bge_m3")
    t_text_model = time.time() - t0
    print(f"Model load: CodeBERT {t_code_model:.1f}s | BGE-M3 {t_text_model:.1f}s")

    tmp = tempfile.mkdtemp(prefix="faiss_bench_")
    try:
        vstore = VectorStore(
            index_dir=os.path.join(tmp, "faiss_index"),
            mapping_path=os.path.join(tmp, "faiss_mapping.json"),
        )
        t0 = time.time()
        added = vstore.index_project_files(
            project_files=corpus,
            project_id="bench_project",
            log_callback=lambda m: print(f"  [{time.time() - t0:7.2f}s] {m}"),
        )
        dt = time.time() - t0
        print(f"\nFAISS indexing of {len(corpus)} files: {dt:.1f}s  (added={added})")
        print(f"  -> per-file average: {dt / max(len(corpus), 1):.2f}s")
        print(f"  -> projected for a 200-file project: {dt / max(len(corpus), 1) * 200 / 60:.1f} min")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
