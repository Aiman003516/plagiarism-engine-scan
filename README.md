# 🛡️ Plagiarism Detection Engine — Standalone

A fully self-contained, production-grade plagiarism detection system with:
- **Multi-language code scanning** (Python AST + Pygments token fingerprinting + CodeBERT neural)
- **Arabic & English text scanning** (TF-IDF weighted composite: 30% title + 30% keywords + 40% body)
- **MinHash + LSH** for O(N) scalable candidate discovery (100K+ files)
- **ChromaDB** vector store with multilingual ensemble embeddings
- **PostgreSQL / SQLite** dual-mode relational storage
- **8 offline ML models** (codebert-base, bge-m3, LaBSE, arabertv02, multilingual-e5, etc.)
- **React frontend** with real-time SSE streaming terminal, Git repo scanning, and executive reports

---

## Quick Start

### 1. Backend (Python / FastAPI)

```bash
cd plagiarism_engine_scan

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set the models directory (points to shared models — no duplication)
# Either set the env var or copy .env.example to .env
set MODELS_DIR=D:\AI engine\models   # Windows CMD
# export MODELS_DIR="D:/AI engine/models"  # Linux/Mac

# Start the backend
uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.
API docs: `http://localhost:8000/docs`

### 2. Frontend (React / Vite)

```bash
cd plagiarism_engine_scan/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The UI will be available at `http://localhost:3000`.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MODELS_DIR` | `../models` (relative) | Path to the ML models directory |
| `DATABASE_URL` | `postgresql://...localhost:5432/plagiarism_engine_db` | PostgreSQL connection (optional) |
| `PLAGIARISM_DATA_DIR` | `./data` | Directory for SQLite DB, ChromaDB, scan history |
| `VITE_API_URL` | `http://127.0.0.1:8000` | Backend API URL for the frontend |

### Database

- **PostgreSQL**: If `psycopg2` is installed and PostgreSQL is running, the engine automatically creates and uses a `plagiarism_engine_db` database.
- **SQLite**: Falls back automatically if PostgreSQL is unavailable. Zero configuration needed.

---

## Project Structure & Architecture

```
plagiarism_engine_scan/
├── app/                       # FastAPI modular application (routers, services, state)
│   ├── routers/               # Plagiarism, projects, analytics, auth, departments routers
│   ├── services/              # Scan orchestration, cloud storage, SSE streaming
│   ├── dependencies.py        # RBAC, user context, database dependencies
│   ├── state.py               # Singleton application state & model lifecycle
│   └── main.py                # FastAPI application initialization & middleware
├── plagiarism_engine/         # Core detection engine (7 specialized modules)
│   ├── code_detector.py       # Pygments + AST + CodeBERT hybrid code scanner
│   ├── text_detector.py       # Arabic/English TF-IDF weighted composite scanner
│   ├── vector_store.py        # ChromaDB + LazyModelPool + multilingual ensemble
│   ├── minhash_index.py       # MinHash + LSH for O(N) candidate discovery
│   ├── extractor.py           # Multi-format extractor (PDF, DOCX, ZIP, code)
│   ├── db.py                  # PostgreSQL / SQLite dual-mode relational storage
│   └── __init__.py            # Public API exports
├── frontend/                  # React + Vite + TypeScript web application
│   ├── src/pages/             # Multi-role portals (Student, Faculty, Dean, Ministry)
│   ├── src/components/        # UI components, sidebars, modals, diff viewers
│   └── src/lib/               # API clients, i18n localization (AR/EN), stores
├── scripts/                   # Operational & database maintenance scripts
│   ├── seed_yemen_academic_hierarchy.py  # Hierarchy seed script
│   ├── migrate_sqlite_to_postgres.py     # SQLite to PostgreSQL migration
│   ├── repair_database_cleanup.py        # DB integrity verification & cleanup
│   ├── purge_excluded_files.py           # Node_modules / build artifact purger
│   └── backfill_fingerprints.py          # MinHash / LSH index backfiller
├── tests/                     # Automated pytest test suites
│   ├── test_persona_journeys.py          # End-to-end multi-role RBAC & scanning journey
│   └── test_*.py                         # Unit and integration test suites
├── backend.py                 # FastAPI Uvicorn entrypoint (delegates to app.main)
├── streamlit_app.py           # Optional lightweight Streamlit demo viewer
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable reference
├── .gitignore                 # Version control exclusion rules
└── README.md                  # Project overview & documentation

Local Offline Folders (Maintained locally, untracked by Git):
├── docs/                      # Comprehensive technical documentation & audits
│   ├── architecture/          # System blueprints, USERS_AND_ROLES, hybrid specs
│   ├── audits/                # Backend, frontend, algorithmic & security audits
│   ├── plans_and_roadmaps/    # Master UI/UX, Arabic support, and migration plans
│   ├── prompts/               # Engineering prompts and references
│   └── research_papers/       # Research papers (BGE-M3, Winnowing, UniXcoder, etc.)
└── qa_tools/                  # Local QA, verification & benchmark assets
    ├── benchmarks/            # Vector search & semantic calibration benchmarks
    ├── confirmation_scripts/  # Manual verification & UI sanity check runners
    ├── screenshots/           # Test & visual audit capture artifacts
    └── test_artifacts/        # Temporary test logs and SQLite test databases
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/system/health` | Health check |
| GET | `/api/plagiarism/projects` | List indexed projects |
| GET | `/api/plagiarism/projects/check?names=...` | Check project existence |
| POST | `/api/plagiarism/upload-scan` | Upload files + scan (JSON) |
| POST | `/api/plagiarism/upload-scan-stream` | Upload files + scan (SSE streaming) |
| POST | `/api/plagiarism/git-scan` | Clone git repo + scan (JSON) |
| POST | `/api/plagiarism/git-scan-stream` | Clone git repo + scan (SSE streaming) |
| POST | `/api/plagiarism/scan` | Scan already-indexed project |
| GET | `/api/plagiarism/history` | Scan history list |
| GET | `/api/plagiarism/history/{id}` | Scan history detail |
| DELETE | `/api/plagiarism/history/{id}` | Delete scan report |
