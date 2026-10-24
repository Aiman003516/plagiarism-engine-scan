# Comprehensive Backend System Architecture & Technical Audit

> **System**: Enterprise Multi-Language Source Code & Academic Text Plagiarism Detection Engine  
> **Location**: `C:\Users\Ayman\Downloads\plagiarism_engine_scan`  
> **Auditor**: Master Systems Analyst & Architecture Team  
> **Target Runtime**: Python 3.12+ / FastAPI / PostgreSQL (with SQLite Fallback) / pgvector / PyTorch  

---

## 1. Executive Summary & Runtime Architecture

The backend of the Plagiarism Detection Engine is an asynchronous, high-throughput analytical platform designed for academic institutions and national education ministries. It processes thousands of heterogeneous source files, detects syntactic and semantic plagiarism across multiple programming languages and natural languages (Arabic & English), and enforces multi-tenant institutional boundaries.

```
                              ┌──────────────────────────────────────────────┐
                              │            FastAPI HTTP / SSE App            │
                              │             (Uvicorn ASGI Server)            │
                              └──────────────────────┬───────────────────────┘
                                                     │
         ┌───────────────────┬───────────────────────┼───────────────────────┬───────────────────┐
         │                   │                       │                       │                   │
┌────────▼─────────┐ ┌───────▼──────────┐ ┌──────────▼────────┐ ┌────────────▼───────┐ ┌─────────▼────────┐
│   Auth & RBAC    │ │ Projects & Teams │ │ Intake / Scanner  │ │  Direct Pairwise   │ │  Dashboard /    │
│  (JWT HS256)     │ │ Institutional DB │ │ Streaming Pipeline│ │  Comparison Engine │ │  Settings Store │
└────────┬─────────┘ └───────┬──────────┘ └──────────┬────────┘ └────────────┬───────┘ └─────────┬────────┘
         │                   │                       │                       │                   │
         └───────────────────┴───────────────────────┼───────────────────────┴───────────────────┘
                                                     │
                                 ┌───────────────────▼───────────────────┐
                                 │   Plagiarism Engine Core Services     │
                                 │  • LazyModelPool (UniXcoder / BGE-M3) │
                                 │  • Winnowing & Pygments AST Lexers    │
                                 │  • Binary Quantization 2-Step Scorer  │
                                 │  • Hybrid Fusion Scoring Engine       │
                                 └───────────────────┬───────────────────┘
                                                     │
                             ┌───────────────────────┴───────────────────────┐
                             │                                               │
                 ┌───────────▼───────────┐                       ┌───────────▼───────────┐
                 │ PostgreSQL & pgvector │                       │ Storage Service Layer │
                 │ • Connection Pooling  │                       │ • Local FS Storage    │
                 │ • 680k+ Fingerprints  │                       │ • Supabase Storage    │
                 └───────────────────────┘                       └───────────────────────┘
```

### Core Runtime Characteristics
- **Server Framework**: FastAPI (`>=0.115, <1.0`), ASGI execution via Uvicorn.
- **Multipart Scale Tuning**: Starlette `MultiPartParser.max_files` and `max_fields` are dynamically overridden to **100,000** to support multi-gigabyte monolithic project folders and monorepos.
- **Asynchronous Concurrency**: Heavy CPU and model-inference tasks run in background worker threads via `asyncio.get_running_loop().run_in_executor(None, ...)` to guarantee zero event-loop blocking.
- **Lifespan Warmup**: A daemon thread initiates asynchronous model preloading on application boot (`app.state._preload_models`), allowing the server to bind to port 8000 immediately while heavy neural models load in the background.

---

## 2. Directory Structure & Module Breakdown

```
plagiarism_engine_scan/
├── app/                             # Web application tier (FastAPI)
│   ├── main.py                      # Application bootstrap, lifespan, CORS, router mounting
│   ├── dependencies.py              # JWT validation, role guards (require_role), security policies
│   ├── state.py                     # Global singletons (SystemDBStore, PgVectorStore, preloading)
│   ├── routers/                     # Endpoint controllers
│   │   ├── auth.py                  # Authentication, login, registration, password force-change
│   │   ├── users.py                 # Multi-institution user management, bulk import
│   │   ├── teams.py                 # Academic student teams, one-time submission token
│   │   ├── projects.py              # Catalog, proposal workflow, semantic search, indexing
│   │   ├── scanner.py               # Intake upload scan, repository clone scan, SSE streaming
│   │   ├── deep_scan.py             # Exhaustive pairwise N×M semantic comparison matrix
│   │   ├── compare.py               # Direct file/folder pairwise comparator & diff generator
│   │   ├── history.py               # Scan reports archive, PDF report export
│   │   ├── dashboard.py             # Administrative KPI metrics, chart data
│   │   └── settings.py              # System configuration persistence
│   └── services/                    # Background orchestrators
│       ├── intake.py                # Winnowing fingerprinting & Zlib compression pipeline
│       ├── scan_sessions.py         # Re-attachable SSE session pub/sub buffering
│       ├── git_clone.py             # Ephemeral git sandbox clone & bloat exclusion
│       └── embeddings.py            # Deep scan on-demand embedding batch generator
│
├── plagiarism_engine/               # Core scientific & algorithmic engine
│   ├── winnowing.py                 # Winnowing algorithm (k=50, w=10, 60-bit hash)
│   ├── code_detector.py             # Pygments abstract tokenization & Python AST parser
│   ├── text_detector.py             # Text TF-IDF, sentence extraction, Arabic normalizer
│   ├── arabic_preprocessor.py       # Tashkeel, Tatweel, Hamza normalization, language detection
│   ├── vector_store.py              # LazyModelPool, embedding model management, dimensional padding
│   ├── fusion_scorer.py             # Hybrid scoring (Winnowing + Semantic), adaptive alpha
│   ├── minhash_index.py             # MinHash LSH sub-linear candidate indexer (128 perms)
│   ├── file_policy.py               # Central file-scope admission policy (code/text vs bloat)
│   ├── config.py                    # Thresholds, floors, and model checkpoint paths
│   ├── db/                          # Database access layer
│   │   ├── connection.py            # PostgreSQL pool & SQLite fallback connection provider
│   │   ├── schema.py                # DDL migrations, tables, indices, baseline seeding
│   │   ├── projects_store.py        # Project records & compressed file blobs
│   │   ├── fingerprint_store.py     # Winnowing fingerprint storage & batch indexers
│   │   ├── users_store.py           # User profiles, bcrypt validation, role filters
│   │   ├── teams_store.py           # Team assignment, submission tokens
│   │   ├── settings_store.py        # Key-value persistent settings
│   │   ├── stats_store.py           # Dashboard aggregation queries
│   │   └── helpers.py               # Zlib text compression/decompression, DSN parsers
│   ├── storage/                     # Blob / Document file storage
│   │   ├── base.py                  # Abstract StorageService interface
│   │   ├── local_storage.py         # Local filesystem storage driver
│   │   └── supabase_storage.py      # Cloud Supabase S3-compatible storage driver
│   └── vectors/                     # Vector operations
│       └── pgvector_store.py        # 1024-d Binary Quantization & 2-step rescoring engine
│
├── scripts/                         # Operational & maintenance utilities
│   ├── seed_yemen_academic_hierarchy.py # Multi-university realistic seeding
│   ├── calibrate_semantic_models.py     # ROC-AUC evaluation & discrimination analysis
│   ├── real_corpus_eval.py              # Benchmark evaluation on real graduation projects
│   ├── bench_vector_search.py           # Latency & throughput vector benchmarks
│   ├── backfill_fingerprints.py         # Fingerprint rebuild utility
│   └── purge_excluded_files.py          # Database bloat cleaner
│
└── tests/                           # Verification test suites
    ├── test_rbac_hardening.py       # Institutional isolation & RBAC test suite
    └── test_engine_and_api.py       # Core algorithmic tests
```

---

## 3. Router & API Endpoint Catalog

Every route in the engine is protected by institutional role guards (`require_role(...)`).

### 3.1 Authentication Router (`app/routers/auth.py`)
- `POST /api/auth/login`: Authenticates either standard staff email or student enrollment number using bcrypt. Returns JWT bearer token with claims `{user_id, email, role, requires_password_change}`.
- `POST /api/auth/register`: Self-registration endpoint (configurable via settings).
- `POST /api/auth/change-password`: Enforces forced password update on first login or user-initiated updates.
- `GET /api/auth/me`: Returns sanitized user profile with institutional metadata (`university_id`, `college_id`, `department_id`).

### 3.2 Users Router (`app/routers/users.py`)
- `GET /api/users`: Filtered user listing. Enforces strict scope:
  - `college_admin`: Only sees users within `caller_record.college_id`.
  - `university_admin`: Only sees users within `caller_record.university_id`.
  - `ministry_admin`: Nationwide view with optional `university_id` / `college_id` query filters.
- `POST /api/users`: Creates accounts. Prevents elevation of privilege: College admins can only create Faculty/Students; University admins cannot create Ministry admins.
- `POST /api/users/bulk-import-students`: High-throughput batch import from CSV/Excel rosters.
- `GET /api/users/{user_id}`, `PUT /api/users/{user_id}`, `DELETE /api/users/{user_id}`: CRUD operations guarded by institutional boundaries, self-deletion locks, and last-superadmin protection.

### 3.3 Teams Router (`app/routers/teams.py`)
- `GET /api/teams`: Returns student teams scoped to caller's college or university. Students see only their own team.
- `POST /api/teams`: Creates student teams with enforced college assignment.
- `POST /api/teams/{team_id}/toggle-submission`: Grants or revokes the one-time proposal submission token for graduation project teams. Guarded by college jurisdiction.
- `POST /api/teams/{team_id}/members`: Adds students to teams after verifying that the student belongs to the same college.
- `DELETE /api/teams/{team_id}/members/{student_id}`: Removes student membership.
- `GET /api/teams/students/search`: Autocomplete student search restricted to caller's college/university.

### 3.4 Projects & Catalog Router (`app/routers/projects.py`)
- `GET /api/plagiarism/projects`: Scoped project catalog. Proposals with `status = "pending_review"` are strictly visible only to staff of that specific college. Approved reference projects are viewable nationwide.
- `POST /api/plagiarism/projects/student-submit`: Student proposal intake. Validates that the team's one-time submission token is active, creates the project record, immediately embeds the abstract with BGE-M3, and locks the token.
- `POST /api/plagiarism/projects/{project_id}/review`: Academic supervisor / committee review (`approve` or `reject` with review notes and optional re-submission token unlock).
- `DELETE /api/plagiarism/projects/{project_id}`: Deletes project, stored file contents, fingerprints, and pgvector embeddings.
- `GET /api/plagiarism/projects/{project_id}/files`: Returns project file tree with optional Zlib-decompressed source text.
- `POST /api/plagiarism/projects/{project_id}/index-embeddings`: On-demand background embedding generator for Deep Scan mode.
- `POST /api/plagiarism/projects/semantic-search`: High-speed vector search across project abstracts and text files using hybrid lexical-semantic matching.

### 3.5 Plagiarism Scanner Router (`app/routers/scanner.py`)
- `POST /api/plagiarism/upload-scan`: Multi-part zip/file folder intake and scan.
- `POST /api/plagiarism/upload-scan-stream`: Real-time SSE streaming intake. Yields granular progress logs, computes Winnowing fingerprints, indexes files, and emits real-time matches.
- `POST /api/plagiarism/scan-git-repo-stream`: Clones remote git repo into an isolated sandbox, filters out non-scannable files, and streams scan progress.
- `GET /api/plagiarism/scan-stream/{project_id}`: Re-attaches to a running or recently completed SSE scan stream using an unguessable capability token.
- `POST /api/plagiarism/scan/abort/{project_id}`: Cancels an in-flight scan via `AbortController` signal.

### 3.6 Direct Pairwise Comparison Router (`app/routers/compare.py`)
- `POST /api/plagiarism/compare-direct-files`: Compares two arbitrary uploaded files (File A vs File B) on the fly without persisting them to the database. Computes Winnowing containment, UniXcoder/BGE-M3 semantic similarity, and unified diff blocks.
- `POST /api/plagiarism/compare-projects`: Compares two existing stored projects, generating an N×M comparison matrix with file-level diff alignments.

### 3.7 Deep Scan Router (`app/routers/deep_scan.py`)
- `POST /api/plagiarism/deep-scan`: Runs an exhaustive, semantic-only deep scan comparing query project vectors against target project vectors in PostgreSQL using 2-step Binary Quantization and Cosine rescoring.

### 3.8 History, Dashboard & Settings (`history.py`, `dashboard.py`, `settings.py`)
- `GET /api/plagiarism/history`: Paginated list of past scan reports with similarity scores, verdicts, and timestamps.
- `GET /api/plagiarism/reports/{query_id}/pdf`: Dynamically renders and streams an official PDF Plagiarism Clearance Certificate with cryptographic verification QR and breakdown.
- `GET /api/dashboard/stats`: Returns overall corpus metrics, fingerprint totals, scanned project counts, and institutional breakdown.
- `GET /api/settings`, `PUT /api/settings`: Manages system parameters, language defaults, and similarity thresholds.

---

## 4. Multi-Tenant Institutional Hierarchy & Scoping

The backend implements a 5-tier hierarchical jurisdiction model:

```
Level 1: Ministry of Higher Education (ministry_admin)
         └─ Nationwide jurisdiction. Can audit all universities, colleges, and projects.
Level 2: University Administration (university_admin)
         └─ Rector / Vice-President level. Governs all colleges within a specific university.
Level 3: College Administration (college_admin)
         └─ Dean level. Manages faculty, departments, and students within a specific college.
Level 4: Faculty Supervisor (faculty)
         └─ Department professor. Manages assigned student teams, toggles submission tokens, reviews proposals.
Level 5: Student (student)
         └─ Submits proposals when authorized by supervisor. Restricted from viewing administrative surfaces.
```

### Institutional Scoping Implementation Rules
1. **User Visibility**: College Admins cannot view or modify faculty/students outside their `college_id`. University Admins cannot view staff outside their `university_id`.
2. **Team Management**: Faculty and College Admins can only view and manage student teams in their own college.
3. **One-Time Proposal Token**: Teams cannot submit graduation proposals unless a faculty supervisor from their college unlocks the token (`submission_allowed = True`). Upon successful proposal submission, the token is automatically consumed (`submission_allowed = False`).
4. **Proposal Review Isolation**: Pending proposals submitted by students of College A are completely invisible to deans and supervisors of College B.

---

## 5. Database Schema & Storage Architecture

The database access layer supports dual engines: **PostgreSQL** (production mode with pgvector) and **SQLite** (lightweight local fallback).

### PostgreSQL Tables & Indices
| Table Name | Primary Key | Key Columns & Types | Description |
| :--- | :--- | :--- | :--- |
| `universities` | `id (TEXT)` | `name (TEXT UNIQUE)`, `code (TEXT)`, `created_at` | Top-level academic institutions |
| `colleges` | `id (TEXT)` | `university_id (FK)`, `name (TEXT)` | Faculties/Colleges belonging to universities |
| `departments` | `id (TEXT)` | `college_id (FK)`, `name (TEXT)` | Academic departments |
| `users` | `id (TEXT)` | `email (TEXT UNIQUE)`, `password_hash (TEXT)`, `role (TEXT)`, `university_id`, `college_id`, `department_id` | Staff, faculty, and student user accounts |
| `students` | `id (TEXT)` | `enrollment_number (TEXT UNIQUE)`, `name`, `team_id`, `college_id`, `university_id` | Enrolled students linked to teams |
| `teams` | `id (TEXT)` | `name (TEXT)`, `college_id (TEXT)`, `submission_allowed (BOOLEAN)` | Graduation project student teams |
| `projects` | `id (TEXT)` | `name`, `title`, `abstract`, `university`, `department`, `year`, `status`, `abstract_embedding`, `abstract_embedding_binary` | Graduation projects & benchmark corpus |
| `project_files`| `id (TEXT)` | `project_id (FK)`, `relative_path`, `file_type`, `content (TEXT)`, `embedding`, `embedding_binary`, `embedding_model` | File records with compressed source content |
| `fingerprint_index` | `id (SERIAL)`| `project_id`, `fingerprint_hash (BIGINT)`, `file_type`, `relative_path`, `token_position` | 60-bit Winnowing fingerprints |
| `scan_reports` | `id (TEXT)` | `query_id`, `target_project_id`, `winnowing_score`, `semantic_score`, `fusion_score`, `verdict` | Historical scan execution reports |
| `settings` | `key (TEXT)` | `value (TEXT)` | Key-value application configuration |

### Indices for High-Throughput Matching
- `idx_fp_hash`: B-tree index on `fingerprint_index(fingerprint_hash)` for instant hash matching.
- `idx_fp_composite`: Composite index on `fingerprint_index(fingerprint_hash, file_type, project_id)`.
- `idx_pf_embedded`: Composite index on `project_files(file_type, embedding_model)` for vector search partitioning.

### Storage Service Abstraction (`plagiarism_engine/storage/`)
Source file bodies are decoupled from primary database tables:
- `LocalStorageService`: Stores files under a dedicated filesystem root partitioned by project ID (`storage_root/{project_id}/{relative_path}`).
- `SupabaseStorageService`: Uploads files to cloud object storage buckets via the Supabase Python SDK.
- Files stored in the database `project_files.content` column are Zlib-compressed (`compress_text()`) to minimize storage footprint.

---

## 6. Security & Cryptographic Mechanisms

1. **Password Security**: Passwords are encrypted using `bcrypt` with automated salt generation. Plaintext passwords are never logged or stored.
2. **JWT Authorization**: Signed using `jose` with `HS256`. The secret key is validated at startup (`validate_jwt_secret`); in production (`APP_ENV=production`), secrets shorter than 32 characters or matching known placeholder strings are rejected.
3. **Self-Lockout Prevention**: Administrative users cannot alter their own roles or delete their own accounts via the API, preventing accidental administrator lockouts.
4. **Last Super-Admin Guard**: The system prevents demoting or deleting the final remaining active `ministry_admin`.
5. **Path Traversal Protection**: Uploaded file paths and git repository paths are normalized and stripped of directory traversal tokens (`..`, `/`, `\`) before storage or sandbox allocation.
6. **Ephemeral Sandbox Isolation**: Remote git clones are executed with depth=1 in temporary directories, immediately stripped of `.git` metadata, scanned in memory, and purged from disk.
