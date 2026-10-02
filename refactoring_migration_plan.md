# Refactoring, Migration & Supervisor Alignment Report

---

## 1. Supervisor Requirements vs What We Built

| Supervisor Requirement | What We Built | Verdict |
|------------------------|---------------|---------|
| **Students**: Search projects, view summaries | ✅ Students can log in with enrollment ID, view projects | ✅ MATCH |
| **Students**: Submit proposals (if extended) | ✅ Students can upload projects (pending approval) | ✅ EXCEEDED |
| **Faculty**: Upload PDFs, trigger similarity checks | ✅ Upload ZIP/files/Git repos, trigger Quick + Deep scan | ✅ EXCEEDED |
| **Faculty**: Approve/reject project titles | ✅ `/api/plagiarism/projects/{id}/approve` endpoint + UI | ✅ MATCH |
| **System Admin**: Manage university data, users | ✅ Full CRUD for users, teams, settings. RBAC enforced. | ✅ MATCH |
| **Document Ingestion**: Extract text from PDFs/Word | ✅ `FileExtractor` handles PDF (pypdf), DOCX, code files, multi-encoding | ✅ EXCEEDED |
| **Indexing & Database**: Store metadata (Title, Abstract, Dept, Year, University) | ✅ `projects` table has all fields + `student_id`, `status`, `team_id` | ✅ EXCEEDED |
| **Indexing & Database**: Store full text vectors | ✅ FAISS stores CodeBERT/BGE-M3 embeddings. pgvector planned. | ✅ MATCH |
| **Semantic Search**: sentence-transformers embeddings | ✅ `vector_store.py` uses SentenceTransformer models | ✅ MATCH |
| **Semantic Search**: pgvector / Qdrant / Faiss | ✅ FAISS implemented. pgvector planned in Hybrid Architecture. | ✅ MATCH |
| **Semantic Search**: Return top matches by cosine similarity | ✅ `search_bulk()` returns top-5 nearest neighbors | ✅ MATCH |
| **Text Matching**: Extract text from PDFs (pypdf) | ✅ `extractor.py` uses `pypdf.PdfReader` | ✅ EXACT MATCH |
| **Text Matching**: TF-IDF + Cosine / LSH | ✅ We use Winnowing (stronger than TF-IDF) + MinHash (LSH variant) | ✅ EXCEEDED |
| **String Matching / Diff**: Highlight exact matching passages | ✅ `DiffViewer.tsx` with side-by-side red `<mark>` highlights | ✅ MATCH |
| **Implementation Step 1**: Database Schema | ✅ 9 tables (projects, files, fingerprints, users, students, teams, etc.) | ✅ EXCEEDED |
| **Implementation Step 2**: Text Extraction Pipeline | ✅ PDF, DOCX, code (Pygments tokenizer), multi-encoding | ✅ EXCEEDED |
| **Implementation Step 3**: Search & Plagiarism Algorithm | ✅ Winnowing + FAISS + MinHash + Adaptive Fusion (planned) | ✅ EXCEEDED |
| **Implementation Step 4**: Web Dashboard & UI | ✅ React 19, Tailwind v4, semantic colors, SSE live streaming | ✅ EXCEEDED |
| **Implementation Step 5**: System Testing & Validation | ⚠️ Manual testing done. No automated test suite yet. | ⚠️ PARTIAL |

### Where We EXCEEDED the Supervisor's Spec
1. **Winnowing** is mathematically stronger than TF-IDF for plagiarism (guaranteed detection threshold).
2. **Live SSE Streaming** with reconnect — supervisor didn't ask for this but it's enterprise-grade.
3. **Hybrid Fusion Algorithm** — supervisor suggested "pgvector OR Faiss". We're building BOTH + a novel fusion layer.
4. **Force Password Change** — enterprise auth pattern not in the spec.
5. **Git Repository Scanning** — supervisor only mentioned file uploads.
6. **Multi-language Code Tokenization** via Pygments — handles Python, Java, C++, JS, etc.

### What's Still Missing
1. **Automated Test Suite** — The supervisor explicitly lists "System Testing & Validation".
2. **Arabic Text Support** — Supervisor mentions "multilingual models if dealing with Arabic text". BGE-M3 supports Arabic, but we haven't tested it.

---

## 2. File Size Audit (The "Exploded Files" Problem)

### Backend
| File | Lines | Status |
|------|------:|--------|
| `backend.py` | **1,826** | 🔴 Way too large. Must be split. |
| `db.py` | **1,347** | 🔴 Way too large. Must be split. |
| `vector_store.py` | 381 | 🟡 Acceptable but could be cleaner |
| `code_detector.py` | 377 | ✅ Good |
| `text_detector.py` | 328 | ✅ Good |
| `extractor.py` | 247 | ✅ Good |
| `minhash_index.py` | 205 | ✅ Good |
| `winnowing.py` | 106 | ✅ Perfect |

### Frontend
| File | Lines | Status |
|------|------:|--------|
| `Plagiarism.tsx` | **1,358** | 🔴 Way too large. Must be split. |
| `PlagiarismAnalysis.tsx` | 542 | 🟡 Borderline |
| `Dashboard.tsx` | 285 | ✅ Good |
| `Projects.tsx` | 283 | ✅ Good |
| `Users.tsx` | 258 | ✅ Good |
| `Teams.tsx` | 252 | ✅ Good |
| `api.ts` | 800 | 🟡 Large but acceptable (it's all API methods) |

### The 3 Critical Files to Split
1. **`backend.py` (1,826 lines)** → Split into 5 router modules
2. **`db.py` (1,347 lines)** → Split into domain-specific stores
3. **`Plagiarism.tsx` (1,358 lines)** → Split into sub-components

---

## 3. Refactoring Strategy (Without Breaking Anything)

### The Golden Rule: Refactoring changes WHERE code lives, never WHAT it does.

### Step 1: Split `backend.py` using FastAPI `APIRouter`

```
BEFORE (1 file, 1826 lines):
  backend.py

AFTER (6 files, same total lines):
  app/
  ├── main.py              (~100 lines) — FastAPI app, CORS, startup
  ├── dependencies.py      (~80 lines)  — JWT auth, require_role(), get_db()
  ├── routers/
  │   ├── auth.py           (~200 lines) — login, change-password, me
  │   ├── users.py          (~250 lines) — CRUD users + students
  │   ├── projects.py       (~300 lines) — upload, list, approve, delete
  │   ├── scanner.py        (~400 lines) — SSE scan, deep-scan, compare
  │   ├── settings.py       (~80 lines)  — get/update settings
  │   └── dashboard.py      (~50 lines)  — stats endpoint
  └── services/
      ├── intake.py          (~200 lines) — _run_intake(), _run_analysis()
      └── git_clone.py       (~100 lines) — _clone_git_repo()
```

Each router file uses:
```python
from fastapi import APIRouter
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
async def login(...):
    ...
```

And `main.py` simply includes them:
```python
from app.routers import auth, users, projects, scanner, settings, dashboard
app.include_router(auth.router)
app.include_router(users.router)
# ... etc
```

### Step 2: Split `db.py`

```
BEFORE: plagiarism_engine/db.py (1,347 lines)

AFTER:
  plagiarism_engine/db/
  ├── __init__.py          — exports SystemDBStore
  ├── connection.py        (~100 lines) — connection management, pool
  ├── schema.py            (~120 lines) — CREATE TABLE statements
  ├── projects_store.py    (~300 lines) — project CRUD + files
  ├── fingerprint_store.py (~200 lines) — fingerprint batch ops
  ├── users_store.py       (~200 lines) — user + student CRUD
  ├── teams_store.py       (~150 lines) — team CRUD
  └── settings_store.py    (~50 lines)  — settings key-value
```

### Step 3: Split `Plagiarism.tsx`

```
BEFORE: frontend/src/pages/Plagiarism.tsx (1,358 lines)

AFTER:
  frontend/src/pages/plagiarism/
  ├── index.tsx             (~100 lines) — main page layout
  ├── UploadSection.tsx     (~200 lines) — file/zip upload form
  ├── GitScanSection.tsx    (~150 lines) — git URL input
  ├── ScanProgress.tsx      (~200 lines) — SSE progress + logs
  ├── ResultsSummary.tsx    (~200 lines) — verdict cards
  ├── ComparisonSection.tsx (~200 lines) — project-vs-project
  └── hooks/
      └── useScanStream.ts  (~150 lines) — SSE connection logic
```

---

## 4. Cloud Migration Plan

### Phase A: PostgreSQL (Replace SQLite)

```
CURRENT:                          TARGET:
┌──────────┐                     ┌──────────────────┐
│  SQLite   │  ──────────────►   │   PostgreSQL     │
│  (local   │                    │   (local OR       │
│   file)   │                    │    Supabase/Neon) │
└──────────┘                     └──────────────────┘
```

Changes needed in `db.py` (or `db/connection.py` after refactor):
- Replace `sqlite3.connect()` with `psycopg2.connect()` or `asyncpg`
- Replace `?` parameter markers with `%s`
- Replace `AUTOINCREMENT` with `SERIAL`
- Add connection pooling (`psycopg2.pool.ThreadedConnectionPool`)
- Read `DATABASE_URL` from environment variable

### Phase B: pgvector (Add Vector Column)

```sql
-- Run once after PostgreSQL migration
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE project_files ADD COLUMN embedding VECTOR(768);

CREATE INDEX idx_files_embedding ON project_files
    USING hnsw (embedding vector_cosine_ops);
```

Changes in `vector_store.py`:
- Add a `PgVectorStore` class that writes/reads embeddings via SQL
- Keep `FAISSStore` class for in-memory speed cache
- Create a `HybridVectorService` that writes to both and searches FAISS-first

### Phase C: Cloud Storage (Replace Local Filesystem)

```
CURRENT:                          TARGET:
┌──────────┐                     ┌──────────────────┐
│  data/    │  ──────────────►   │  Supabase Storage │
│  (local   │                    │  or AWS S3         │
│   disk)   │                    │  (cloud bucket)    │
└──────────┘                     └──────────────────┘
```

Create a `StorageService` abstraction:
```python
class StorageService:
    def save_file(self, path: str, content: bytes) -> str: ...
    def read_file(self, path: str) -> bytes: ...
    def delete_file(self, path: str) -> None: ...

class LocalStorage(StorageService): ...    # Current behavior
class SupabaseStorage(StorageService): ... # Cloud behavior
```

---

## 5. Does the Hybrid Architecture Cause Issues During Migration?

### Short Answer: No, it actually HELPS.

| Concern | Reality |
|---------|---------|
| Will FAISS conflict with pgvector? | No. They are completely independent. FAISS reads/writes `.faiss` files. pgvector reads/writes SQL columns. They never touch each other's data. |
| Will refactoring break the hybrid? | No. The hybrid architecture actually REQUIRES the refactor. `vector_store.py` must be split into `FAISSStore` + `PgVectorStore` + `HybridVectorService`. This is cleaner AFTER the refactor. |
| Can we migrate incrementally? | Yes. Phase A (Postgres) works without pgvector. Phase B adds the vector column. Phase C adds cloud storage. Each phase is independently testable. |
| What if FAISS is unavailable? | The `HybridVectorService` falls back to pgvector automatically. On serverless (no FAISS), it uses pgvector only. Zero code changes needed. |

### The Recommended Order

```
1. Refactor backend.py → routers/        (no logic changes, just moving code)
2. Refactor db.py → db/ package          (no logic changes, just moving code)
3. Refactor Plagiarism.tsx → components   (no logic changes, just moving code)
4. Test everything still works            (manual + automated)
5. Migrate SQLite → PostgreSQL            (change connection layer only)
6. Add pgvector column + HybridVectorService
7. Add cloud storage abstraction
8. Deploy to Supabase / VPS
```

> **Key Insight**: We refactor FIRST (steps 1-4), then migrate (steps 5-8).  
> Refactoring with a 1,826-line file is dangerous.  
> Refactoring into clean 200-line modules is safe.  
> Migrating clean 200-line modules is trivial.
