# Phase 4 Goal: PostgreSQL + pgvector Migration

## Objective
Replace SQLite with PostgreSQL and add pgvector for vector storage. This is the database migration phase — the most critical and delicate phase in the roadmap.

## Context
Read `MASTER_ROADMAP.md` in this repo for the full project context. This is Phase 4 of 6.
Phases 2 (refactoring) and 3 (Arabic) must be completed before starting this phase.

## Prerequisites
- PostgreSQL 15+ installed locally OR a Supabase/Neon project created
- `psycopg2-binary` and `pgvector` Python packages added to `requirements.txt`
- The `vector` extension enabled on the PostgreSQL database: `CREATE EXTENSION IF NOT EXISTS vector;`

## Tasks

### Task 1: Add PostgreSQL Dependencies

In `requirements.txt`, add:
```
psycopg2-binary>=2.9.9
pgvector>=0.3.0
```

### Task 2: Update Connection Layer

In `plagiarism_engine/db/connection.py` (created in Phase 2):
- Read `DATABASE_URL` from environment variable
- If `DATABASE_URL` starts with `postgresql://` → use `psycopg2`
- If `DATABASE_URL` is absent or starts with `sqlite://` → keep SQLite (backward compatible)
- Add connection pooling: `psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10)`
- This fixes Bug 9 (DB connection pooling) from the audit

```python
import os
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/plagiarism.db")

if DATABASE_URL.startswith("postgresql://"):
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool
    pool = ThreadedConnectionPool(2, 10, DATABASE_URL)
    def _get_conn():
        return pool.getconn()
    def _put_conn(conn):
        pool.putconn(conn)
else:
    import sqlite3
    # ... existing SQLite logic
```

### Task 3: Update SQL Syntax

Go through ALL SQL queries in the db/ package and make them compatible with both PostgreSQL and SQLite:
- Replace `?` parameter markers with `%s` for PostgreSQL (or use a helper that adapts)
- Replace `AUTOINCREMENT` with `SERIAL` for PostgreSQL
- Replace `INSERT OR REPLACE` with `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL upsert)
- Replace `datetime('now')` with `NOW()` for PostgreSQL
- Replace `LIKE` (case-sensitive in Postgres) with `ILIKE` where needed
- Handle `BOOLEAN` type (SQLite uses 0/1, Postgres uses true/false)

Strategy: Create a `dialect` variable (`"postgres"` or `"sqlite"`) and use it to select the correct SQL variant. Or use parameterized query builders.

### Task 4: Update Schema

In `plagiarism_engine/db/schema.py`:
- Add the `VECTOR(768)` column to `project_files` table (only for PostgreSQL)
- Add the pgvector HNSW index:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_files_embedding
      ON project_files USING hnsw (embedding vector_cosine_ops)
      WITH (m = 16, ef_construction = 64);
  ```
- Ensure `ensure_tables()` runs both SQLite and PostgreSQL DDL correctly

### Task 5: Build PgVectorStore

Create `plagiarism_engine/vectors/pgvector_store.py`:
- `store_embedding(file_id, embedding)` — UPDATE the `embedding` column in `project_files`
- `search_similar(query_vector, top_k, exclude_project_id)` — use `<=>` cosine distance operator
- `delete_project_embeddings(project_id)` — SET embedding = NULL for all files in project
- `count_embeddings()` — COUNT(*) WHERE embedding IS NOT NULL

### Task 6: Build HybridVectorService

Create `plagiarism_engine/vectors/hybrid_service.py`:
- On `.store()`: write to pgvector FIRST, then FAISS
- On `.search()`: try FAISS first (fast), fall back to pgvector if FAISS unavailable
- On `.delete()`: delete from both
- On server startup: `hydrate_faiss_from_db()` — load all vectors from pgvector into FAISS
- Configurable via `VECTOR_BACKEND` env var: `"hybrid"` (both), `"pgvector"` (cloud only), `"faiss"` (local only)

### Task 7: Data Migration Script

Create `scripts/migrate_sqlite_to_postgres.py`:
- Read all data from the SQLite database
- Insert it into the PostgreSQL database
- Migrate FAISS vectors into the pgvector column
- Print progress and row counts for verification

### Task 8: Create `.env.example`

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/plagiarism_engine

# Vector backend: "hybrid" (FAISS + pgvector), "pgvector" (cloud), "faiss" (local)
VECTOR_BACKEND=hybrid

# JWT Secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
JWT_SECRET=your-secret-here

# Models directory
MODELS_DIR=./models
```

### Task 9: Verify

1. Create a local PostgreSQL database: `createdb plagiarism_engine`
2. Set `DATABASE_URL=postgresql://localhost:5432/plagiarism_engine`
3. Start the backend — tables should be created automatically
4. Run the migration script to move SQLite data to Postgres
5. Test: login, upload files, run scan, deep scan — all must work identically
6. Verify: check that embeddings are stored in the `embedding` VECTOR column
7. Test: unset DATABASE_URL → system should fall back to SQLite (backward compatible)
8. Run frontend TypeScript check: `cd frontend && npx tsc --noEmit`
9. Git push

## Success Criteria
- [ ] System works with PostgreSQL (set via DATABASE_URL)
- [ ] System still works with SQLite (when DATABASE_URL is absent)
- [ ] pgvector stores embeddings in the `project_files.embedding` column
- [ ] FAISS hydrates from pgvector on startup
- [ ] Connection pooling is active (Bug 9 resolved)
- [ ] Migration script successfully moves SQLite data to Postgres
- [ ] `.env.example` created with all config variables
- [ ] Git pushed to GitHub
