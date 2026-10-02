# MASTER ROADMAP — Ministry Plagiarism Detection Engine

> **Project**: Ministry of Higher Education — Graduation Project Plagiarism Detection Engine  
> **Author**: Aiman  
> **University**: Ibb University, Yemen  
> **Date**: October 2, 2026  
> **Version**: 2.0 (Unified Master Document)

> [!IMPORTANT]
> This is the **single source of truth** for the entire project roadmap.
> It merges the Architecture Hardening Plan, Refactoring Strategy, Arabic Support Plan,
> Hybrid Architecture Spec, and Cloud Migration Plan into one unified document.
> All previous standalone plan files are superseded by this document.

---

## Table of Contents

1. [Supervisor Alignment](#1-supervisor-alignment)
2. [Current System Status](#2-current-system-status)
3. [Execution Roadmap (6 Phases)](#3-execution-roadmap)
4. [Phase 1 — Bug Fixes (COMPLETED)](#4-phase-1--bug-fixes-completed)
5. [Phase 2 — Codebase Refactoring](#5-phase-2--codebase-refactoring)
6. [Phase 3 — Arabic Language Support](#6-phase-3--arabic-language-support)
7. [Phase 4 — PostgreSQL + pgvector Migration](#7-phase-4--postgresql--pgvector-migration)
8. [Phase 5 — Cloud Storage & Serverless Readiness](#8-phase-5--cloud-storage--serverless-readiness)
9. [Phase 6 — Hybrid Fusion Algorithm](#9-phase-6--hybrid-fusion-algorithm)
10. [System Architecture (Final Vision)](#10-system-architecture-final-vision)
11. [Hybrid Vector Architecture: FAISS + pgvector](#11-hybrid-vector-architecture)
12. [Adaptive Fusion Scoring Algorithm](#12-adaptive-fusion-scoring-algorithm)
13. [Deployment Modes](#13-deployment-modes)
14. [Pros and Cons](#14-pros-and-cons)
15. [Time Complexity Summary](#15-time-complexity-summary)
16. [Database Schema (9 Tables)](#16-database-schema)
17. [File Size Audit](#17-file-size-audit)

---

## 1. Supervisor Alignment

| Supervisor Requirement | What We Built | Verdict |
|------------------------|---------------|---------|
| **Students**: Search projects, view summaries | Students log in with enrollment ID, view projects | ✅ MATCH |
| **Students**: Submit proposals (if extended) | Students upload projects (pending approval) | ✅ EXCEEDED |
| **Faculty**: Upload PDFs, trigger similarity checks | Upload ZIP/files/Git repos, Quick + Deep scan | ✅ EXCEEDED |
| **Faculty**: Approve/reject project titles | `/api/plagiarism/projects/{id}/approve` endpoint + UI | ✅ MATCH |
| **System Admin**: Manage university data, users | Full CRUD for users, teams, settings. RBAC enforced. | ✅ MATCH |
| **Document Ingestion**: Extract text from PDFs/Word | `FileExtractor`: PDF (pypdf), DOCX, code, multi-encoding | ✅ EXCEEDED |
| **Indexing & Database**: Store metadata + vectors | 9 tables + FAISS embeddings. pgvector planned. | ✅ MATCH |
| **Semantic Search**: sentence-transformers / pgvector / FAISS | FAISS + SentenceTransformer. Hybrid pgvector planned. | ✅ MATCH |
| **Text Matching**: TF-IDF + Cosine / LSH | Winnowing (stronger than TF-IDF) + MinHash (LSH variant) | ✅ EXCEEDED |
| **String Matching / Diff**: Highlight matching passages | `DiffViewer.tsx` with side-by-side red highlights | ✅ MATCH |
| **System Testing & Validation** | Manual testing done. Automated tests pending. | ⚠️ PARTIAL |

### Where We EXCEEDED the Supervisor's Spec
1. **Winnowing** — mathematically guaranteed detection threshold (stronger than TF-IDF)
2. **Live SSE Streaming** — with reconnect support (enterprise-grade)
3. **Hybrid Fusion Algorithm** — supervisor said "pgvector OR Faiss"; we build BOTH + novel fusion
4. **Force Password Change** — enterprise auth pattern not in the spec
5. **Git Repository Scanning** — supervisor only mentioned file uploads
6. **Multi-language Code Tokenization** — Pygments handles Python, Java, C++, JS, etc.

### What's Still Missing
1. **Automated Test Suite** — supervisor explicitly lists "System Testing & Validation"
2. **Arabic Text Support** — supervisor mentions "multilingual models if dealing with Arabic text"

---

## 2. Current System Status

### Bug Fix Status (8/9 Complete)

| # | Bug | Status |
|---|-----|--------|
| 1 | Winnowing Dead Zone (15-30 line files invisible) | ✅ Fixed |
| 2 | FAISS Empty Index (Deep Scan broken) | ✅ Fixed |
| 3 | Faculty role whitelist | ✅ Fixed |
| 4 | Git-tracked temp files | ✅ Fixed |
| 5 | Git OAuth token leak | ✅ Fixed |
| 6 | PDF/DOCX upload garbling | ✅ Fixed |
| 7 | Hardcoded JWT secret | ✅ Fixed |
| 8 | Hardcoded models path | ✅ Fixed |
| 9 | DB connection pooling | ⏸️ Deferred to Phase 4 |

### Tech Stack
- **Backend**: FastAPI, Python 3.11+, uvicorn
- **Frontend**: React 19, Vite 6, Tailwind v4, Zustand 5, Framer Motion 12
- **Database**: SQLite (migrating to PostgreSQL)
- **Vector Search**: FAISS (adding pgvector)
- **AI Models**: CodeBERT, BGE-M3, all-MiniLM-L6-v2
- **Algorithms**: Winnowing (k=50), MinHash/LSH, difflib

---

## 3. Execution Roadmap

```
Phase 1 ✅ Bug Fixes                              [DONE]
   │
Phase 2    Codebase Refactoring                    [NEXT]
   │       Split backend.py, db.py, Plagiarism.tsx
   │       into clean modular files (~200 lines each)
   │
Phase 3    Arabic Language Support
   │       Arabic preprocessor, RTL diff viewer,
   │       Winnowing Arabic tokenizer, i18n
   │
Phase 4    PostgreSQL + pgvector Migration
   │       Replace SQLite → Postgres,
   │       add VECTOR(768) column, connection pool
   │
Phase 5    Cloud Storage & Serverless
   │       StorageService abstraction,
   │       Supabase/S3 integration
   │
Phase 6    Hybrid Fusion Algorithm
           Adaptive α-weighted scoring,
           Winnowing + Semantic fusion
```

> [!IMPORTANT]
> **Each phase is independently deployable and testable.**
> Never start Phase N+1 until Phase N is verified working.

---

## 4. Phase 1 — Bug Fixes (COMPLETED) ✅

All critical bugs discovered during the full system audit have been resolved.
Commit `a5285c3` on GitHub contains all fixes. See Section 2 for the full list.

---

## 5. Phase 2 — Codebase Refactoring

> **Goal**: Split the 3 oversized files into clean modules WITHOUT changing any logic.
> **Golden Rule**: Refactoring changes WHERE code lives, never WHAT it does.

### 5.1 Split `backend.py` (1,826 lines → 10 files)

```
BEFORE:
  backend.py (1,826 lines)

AFTER:
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

### 5.2 Split `db.py` (1,347 lines → 7 files)

```
BEFORE:
  plagiarism_engine/db.py (1,347 lines)

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

### 5.3 Split `Plagiarism.tsx` (1,358 lines → 7 files)

```
BEFORE:
  frontend/src/pages/Plagiarism.tsx (1,358 lines)

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

## 6. Phase 3 — Arabic Language Support

> **Why**: This is a Yemeni university system. Arabic is the primary language.
> A plagiarism engine that only detects English copying is fundamentally incomplete.

### 6.1 Arabic Readiness Matrix

| Component | English | Arabic | What's Needed |
|-----------|---------|--------|---------------|
| PDF Extraction | ✅ | ⚠️ Partial | Fix reversed character order |
| DOCX Extraction | ✅ | ✅ Works | Nothing |
| Winnowing | ✅ | ⚠️ Broken | Arabic tokenizer + normalization |
| BGE-M3 (Semantic) | ✅ | ✅ Ready | Just needs clean Arabic input |
| Diff Viewer | ✅ | ❌ Broken | Add RTL text direction support |
| Stop Words | ✅ | ❌ Missing | Arabic stop word list |
| UI Labels | ✅ | ⚠️ Partial | Complete Arabic i18n translations |

### 6.2 New File: `plagiarism_engine/arabic_preprocessor.py`

```python
"""
Arabic text preprocessing for plagiarism detection.
- Diacritics removal (تشكيل): فَتْحَة → فتحة
- Tatweel removal (kashida): عـــربي → عربي
- Hamza normalization: إ أ آ → ا
- Arabic stop words removal
- Language auto-detection (Arabic / English / Mixed)
"""
import re

DIACRITICS = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0656-\u065F\u0670]')
TATWEEL = re.compile(r'\u0640')
HAMZA_MAP = str.maketrans({
    '\u0622': '\u0627', '\u0623': '\u0627',
    '\u0625': '\u0627', '\u0671': '\u0627',
})

ARABIC_STOP_WORDS = {
    'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'ذلك', 'تلك',
    'التي', 'الذي', 'هو', 'هي', 'هم', 'هن', 'أن', 'إن', 'كان', 'كانت',
    'يكون', 'تكون', 'لا', 'لم', 'لن', 'قد', 'ما', 'بعد', 'قبل', 'بين',
    'حتى', 'كل', 'بعض', 'غير', 'أو', 'ثم', 'إذا', 'لكن', 'أما', 'أي',
    'عند', 'منذ', 'حول', 'خلال', 'ضد', 'نحو', 'فوق', 'تحت', 'أمام', 'وراء',
}

def normalize_arabic(text: str) -> str:
    text = DIACRITICS.sub('', text)
    text = TATWEEL.sub('', text)
    text = text.translate(HAMZA_MAP)
    return text

def tokenize_arabic(text: str) -> list[str]:
    normalized = normalize_arabic(text)
    words = re.findall(r'[\u0600-\u06FF]+|[a-zA-Z]+', normalized)
    return [w for w in words if w not in ARABIC_STOP_WORDS and len(w) > 1]

def detect_language(text: str) -> str:
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    total = arabic_chars + latin_chars
    if total == 0: return "unknown"
    ratio = arabic_chars / total
    if ratio > 0.7: return "arabic"
    elif ratio < 0.3: return "english"
    else: return "mixed"
```

### 6.3 Winnowing Arabic Integration

Update `compute_text_fingerprints()` to auto-detect language and route to the
correct tokenizer:

```python
def compute_text_fingerprints(self, text):
    from plagiarism_engine.arabic_preprocessor import detect_language, tokenize_arabic
    lang = detect_language(text)
    if lang == "arabic":
        tokens = tokenize_arabic(text)
    elif lang == "mixed":
        tokens = tokenize_arabic(text) + preprocess_text(text).split()
    else:
        tokens = preprocess_text(text).split()
    # ... rest of the function (small-file bypass + winnowing)
```

### 6.4 Arabic PDF Fix

Add reversed-text detection and correction to `FileExtractor.extract_text_from_pdf()`.
Some Arabic PDFs generated by certain tools extract text in reversed word order.

### 6.5 RTL Diff Viewer

Add `dir="rtl"` dynamically to `DiffViewer.tsx` based on Arabic character detection.
Use `Noto Sans Arabic` font for Arabic text rendering.

### 6.6 Arabic vs English — Why Fusion Matters Here

| Plagiarism Scenario | Winnowing | BGE-M3 Semantic |
|---------------------|-----------|-----------------|
| Copy Arabic paragraph word-for-word | ✅ Catches | ✅ Catches |
| Replace Arabic words with synonyms | ❌ Misses | ✅ Catches |
| Translate English paper to Arabic | ❌ Misses | ✅ Catches |
| Translate Arabic paper to English | ❌ Misses | ✅ Catches |
| Copy code with Arabic comments | ✅ Code caught | ✅ Both caught |

**Estimated effort: ~9 hours**

---

## 7. Phase 4 — PostgreSQL + pgvector Migration

### 7.1 Replace SQLite with PostgreSQL

Changes in `db/connection.py` (after refactor):
- Replace `sqlite3.connect()` → `psycopg2.connect()` or `asyncpg`
- Replace `?` parameter markers → `%s`
- Replace `AUTOINCREMENT` → `SERIAL`
- Add `psycopg2.pool.ThreadedConnectionPool` (fixes Bug 9)
- Read `DATABASE_URL` from environment variable

### 7.2 Add pgvector Extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE project_files ADD COLUMN embedding VECTOR(768);
CREATE INDEX idx_files_embedding ON project_files
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 7.3 Build the HybridVectorService

Split `vector_store.py` into:

```
plagiarism_engine/vectors/
├── __init__.py
├── faiss_store.py          — Current FAISS logic (speed cache)
├── pgvector_store.py       — New pgvector read/write via SQL
└── hybrid_service.py       — Write-through: pgvector first, then FAISS
                              Search: FAISS first, fall back to pgvector
```

---

## 8. Phase 5 — Cloud Storage & Serverless Readiness

### 8.1 Storage Abstraction

```python
class StorageService:
    def save_file(self, path: str, content: bytes) -> str: ...
    def read_file(self, path: str) -> bytes: ...
    def delete_file(self, path: str) -> None: ...

class LocalStorage(StorageService): ...     # Current behavior
class SupabaseStorage(StorageService): ...  # Cloud behavior
```

### 8.2 Environment-Driven Configuration

```env
# .env for local development
DATABASE_URL=postgresql://localhost:5432/plagiarism_engine
STORAGE_BACKEND=local
VECTOR_BACKEND=hybrid  # faiss+pgvector

# .env for Supabase deployment
DATABASE_URL=postgresql://xxx.supabase.co:5432/postgres
STORAGE_BACKEND=supabase
VECTOR_BACKEND=pgvector  # FAISS unavailable on serverless
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbG...
```

---

## 9. Phase 6 — Hybrid Fusion Algorithm

### 9.1 The Formula

```
S_final(A, B) = α · S_winnowing(A, B) + (1 - α) · S_semantic(A, B)
```

### 9.2 Adaptive Weight (α) Rules

| File Characteristic | α Value | Reasoning |
|---------------------|---------|-----------|
| Code file (`.py`, `.java`, `.cpp`) | 0.6 | Code has rigid structure; exact matching is strong |
| Text file (`.txt`, `.md`, `.docx`) | 0.3 | Students paraphrase text; semantics matter more |
| Small file (< k tokens) | 1.0 | Only exact match; semantics unreliable on tiny data |
| Mixed project (code + docs) | 0.5 | Balanced weight for mixed content |
| PDF academic paper | 0.2 | Heavy paraphrasing expected; semantics dominate |
| Arabic text document | 0.25 | Arabic has rich synonyms; semantics are critical |

### 9.3 Verdict Thresholds

| Final Score | Verdict | Color | Action |
|-------------|---------|-------|--------|
| 0% – 20% | SAFE | Green | No action needed |
| 21% – 50% | LOW | Yellow | Manual review recommended |
| 51% – 75% | HIGH | Orange | Likely plagiarism, investigate |
| 76% – 100% | CRITICAL | Red | Almost certain plagiarism |

### 9.4 Implementation (Reference Code)

```python
def compute_fusion_score(file_a_content, file_b_content,
                         file_a_embedding, file_b_embedding,
                         file_type, token_count, winnowing_engine):
    # 1. Winnowing similarity (Jaccard)
    fp_a = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_a_content))
    fp_b = set(h for h, _ in winnowing_engine.compute_text_fingerprints(file_b_content))
    s_winnowing = winnowing_engine.jaccard_similarity(fp_a, fp_b)

    # 2. Semantic similarity (Cosine)
    from numpy.linalg import norm
    s_semantic = float(np.dot(file_a_embedding, file_b_embedding) /
                       (norm(file_a_embedding) * norm(file_b_embedding)))
    s_semantic = max(0.0, s_semantic)

    # 3. Adaptive alpha
    if token_count < winnowing_engine.k:    alpha = 1.0
    elif file_type == "code":               alpha = 0.6
    elif file_type == "text":               alpha = 0.3
    else:                                   alpha = 0.5

    # 4. Fuse
    s_final = alpha * s_winnowing + (1 - alpha) * s_semantic

    # 5. Verdict
    if s_final >= 0.76:   verdict = "CRITICAL"
    elif s_final >= 0.51: verdict = "HIGH"
    elif s_final >= 0.21: verdict = "LOW"
    else:                 verdict = "SAFE"

    return {
        "winnowing_score": round(s_winnowing * 100, 2),
        "semantic_score": round(s_semantic * 100, 2),
        "fusion_score": round(s_final * 100, 2),
        "alpha": alpha, "verdict": verdict,
        "method": "hybrid_fusion_v1",
    }
```

---

## 10. System Architecture (Final Vision)

```
┌──────────────────────────────────────────────────────────────────┐
│                        PROJECT UPLOAD                            │
│                                                                  │
│   Raw Files → FileExtractor → Clean Text                         │
│                   │                                              │
│           Language Detection                                     │
│           (Arabic / English / Mixed)                             │
│                   │                                              │
│        ┌──────────┴──────────┐                                   │
│        ▼                     ▼                                   │
│  Winnowing Engine       CodeBERT / BGE-M3                        │
│  (Arabic or English     (Multilingual                            │
│   tokenizer)             Embeddings)                             │
│        │                     │                                   │
│        ▼                     ├──────────────────┐                │
│  fingerprint_index      ┌───▼───┐          ┌───▼───┐            │
│  (PostgreSQL)           │pgvector│          │ FAISS │            │
│                         │(Source │          │(Speed │            │
│                         │of Truth)│         │ Cache)│            │
│                         └───┬───┘          └───┬───┘            │
│                             └────────┬─────────┘                 │
│                                      ▼                           │
│                           Adaptive Fusion Engine                 │
│                           S = α·Winnowing + (1-α)·Semantic       │
│                                      │                           │
│                                      ▼                           │
│                           Final Score + Verdict                  │
│                           (SAFE / LOW / HIGH / CRITICAL)         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 11. Hybrid Vector Architecture

### Write-Through Synchronization

1. **Write to pgvector FIRST** (source of truth, ACID, durable)
2. **Write to FAISS SECOND** (speed cache, volatile)
3. If FAISS fails → system continues via pgvector fallback
4. On server startup → FAISS re-hydrated from pgvector

### Search Orchestration

```python
def search_similar(query_vector, top_k=10):
    if faiss_index is not None and faiss_index.ntotal > 0:
        return faiss_search(query_vector, top_k)   # ~0.5ms
    else:
        return pgvector_search(query_vector, top_k) # ~15ms (fallback)
```

### pgvector SQL Examples

```sql
-- Top 10 similar files across all projects
SELECT pf.project_id, pf.relative_path,
       1 - (pf.embedding <=> query_embedding) AS cosine_similarity
FROM project_files pf
WHERE pf.project_id != 'current_project_id'
ORDER BY pf.embedding <=> query_embedding
LIMIT 10;

-- Filtered: only within a specific college
SELECT pf.project_id, pf.relative_path,
       1 - (pf.embedding <=> query_embedding) AS cosine_similarity
FROM project_files pf
JOIN projects p ON p.id = pf.project_id
WHERE p.university = 'Ibb University'
ORDER BY pf.embedding <=> query_embedding
LIMIT 10;
```

---

## 12. Adaptive Fusion Scoring Algorithm

See Section 9 for the complete formula, weight rules, verdict thresholds,
and reference implementation.

**Research Novelty**: Most plagiarism engines use a single method. This system
is the first to combine Winnowing (lexical) + FAISS/pgvector (semantic) through
an adaptive α-weighted fusion layer that adjusts its behavior based on file type,
size, and language — including full Arabic support.

---

## 13. Deployment Modes

| Mode | Database | Vectors | Storage | Speed |
|------|----------|---------|---------|-------|
| **Local Dev** | SQLite | FAISS only | Local disk | Maximum |
| **VPS** (Recommended) | PostgreSQL | pgvector + FAISS | Local/Volume | Near-maximum |
| **Serverless** | Supabase/Neon | pgvector only | Supabase Storage | Good (~15-80ms) |

---

## 14. Pros and Cons

### Pros
| # | Advantage | Detail |
|---|-----------|--------|
| 1 | Maximum Speed | FAISS: ~0.5ms per 100K vectors |
| 2 | Cloud Persistence | pgvector inside PostgreSQL, zero data loss |
| 3 | SQL Filtering | `WHERE college = 'X'` in vector queries |
| 4 | Graceful Degradation | FAISS down → pgvector fallback, transparent |
| 5 | Deployment Flexibility | Same code on laptop, VPS, or Supabase |
| 6 | Research Novelty | Adaptive Fusion Algorithm is a genuine contribution |
| 7 | Scalability | pgvector HNSW → millions; FAISS IVF → billions |
| 8 | Cost Efficiency | No Pinecone subscription needed |

### Cons (with Mitigations)
| # | Disadvantage | Mitigation |
|---|-------------|------------|
| 1 | Double write overhead | Write pgvector first (async), FAISS second |
| 2 | RAM consumption (FAISS) | Configurable `FAISS_MAX_VECTORS` limit |
| 3 | Consistency risk | FAISS re-hydrated from pgvector on startup |
| 4 | Cold start (serverless) | pgvector HNSW keeps latency under 80ms |
| 5 | Code complexity | Single `VectorSearchService` interface abstracts both |
| 6 | FAISS not ACID | FAISS is expendable cache; pgvector is source of truth |
| 7 | Model size (400MB+) | Pre-compute embeddings on VPS, store in pgvector |
| 8 | HNSW build time | `CREATE INDEX CONCURRENTLY` during off-peak hours |

---

## 15. Time Complexity Summary

| Operation | Winnowing | FAISS (Flat) | FAISS (IVF) | pgvector (HNSW) |
|-----------|-----------|-------------|-------------|-----------------|
| Index 1 file | O(N) | O(d) | O(d) | O(d·log N) |
| Search 10K | O(S₁+S₂) | O(N·d) ≈ 0.5ms | O(√N·d) ≈ 0.1ms | O(log N·d) ≈ 15ms |
| Search 1M | O(S₁+S₂) | O(N·d) ≈ 50ms | O(√N·d) ≈ 5ms | O(log N·d) ≈ 80ms |
| Filtered search | N/A | ❌ | ❌ | ✅ O(log N·d) |
| Delete project | O(1) | O(N) rebuild | O(N) rebuild | O(1) per row |

Where: N = total vectors, d = dimension (768), S₁/S₂ = fingerprint set sizes

---

## 16. Database Schema

9 tables: `projects`, `project_files`, `papers`, `scan_reports`,
`fingerprint_index`, `users`, `students`, `teams`, `settings`.

After Phase 4 migration, `project_files` gains a `VECTOR(768)` column for pgvector.

---

## 17. File Size Audit

### Files That Must Be Split (Phase 2)
| File | Current Lines | Target |
|------|:------------:|--------|
| `backend.py` | 1,826 🔴 | → 10 router/service modules (~200 each) |
| `db.py` | 1,347 🔴 | → 7 store modules (~200 each) |
| `Plagiarism.tsx` | 1,358 🔴 | → 7 component files (~200 each) |

### Files That Are Fine
| File | Lines | Status |
|------|:-----:|--------|
| `vector_store.py` | 381 | 🟡 Will be split in Phase 4 |
| `code_detector.py` | 377 | ✅ |
| `text_detector.py` | 328 | ✅ |
| `extractor.py` | 247 | ✅ |
| `minhash_index.py` | 205 | ✅ |
| `winnowing.py` | 106 | ✅ Perfect |
| `Dashboard.tsx` | 285 | ✅ |
| `Projects.tsx` | 283 | ✅ |
| `Users.tsx` | 258 | ✅ |
| `Teams.tsx` | 252 | ✅ |

---

> **This document is the single source of truth for the project roadmap.**
> All decisions, architectures, and execution orders are defined here.
> Last updated: October 2, 2026.
