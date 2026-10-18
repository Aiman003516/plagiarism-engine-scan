# Unified Postgres Implementation Plan

## Phase 1: Database Schema Modernization
- [x] Modify `plagiarism_engine/db/schema.py` to add `embedding_binary BIT(1024)` to `project_files`.
- [x] Retain `embedding` (`VECTOR(1024)` / JSON `float32[1024]`) for full-precision rescoring (with 768-dim CodeBERT zero-padded to 1024-dim).

## Phase 2: Python Quantization & 2-Step Rescoring
- [x] Update `PgVectorStore` in `plagiarism_engine/vectors/pgvector_store.py`.
- [x] Implement binary quantization (`float32` > 0 becomes `1`, else `0`).
- [x] Implement the 2-Step Rescoring Query using PostgreSQL native `bit_count(embedding_binary # query_binary)` for Hamming Distance matching + exact float32 Cosine Similarity rescoring.

## Phase 3: Gut FAISS and Refactor VectorStore
- [x] Strip all `faiss` dependencies and local index logic out of `plagiarism_engine/vector_store.py`.
- [x] Convert `VectorStore` into a pure proxy that handles `LazyModelPool` embedding generation and directly pushes to/searches from `PgVectorStore`.
- [x] Ensure `index_project_files`, `search_bulk`, `count_project_vectors`, and `delete_project` maintain the exact same Python API to prevent breaking `app/services/intake.py` and `app/routers/deep_scan.py`.

## Phase 4: App Initialization Cleanup
- [x] Remove FAISS `hydrate_faiss_from_db()` logic from `app/main.py`.
- [x] Remove any legacy hybrid code.

This plan guarantees 100% feature parity without breaking existing backend/frontend contracts.

