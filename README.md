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

## Architecture

```
plagiarism_engine_scan/
├── plagiarism_engine/         # Core detection engine (7 modules)
│   ├── code_detector.py       # Pygments + AST + CodeBERT hybrid code scanner
│   ├── text_detector.py       # Arabic/English TF-IDF weighted composite
│   ├── vector_store.py        # ChromaDB + LazyModelPool + multilingual ensemble
│   ├── minhash_index.py       # MinHash + LSH for O(N) candidate discovery
│   ├── extractor.py           # PDF/DOCX/code file extraction
│   ├── db.py                  # PostgreSQL/SQLite dual-mode storage
│   └── __init__.py            # Public API exports
├── frontend/                  # React/Vite/TypeScript UI
│   └── src/pages/Plagiarism.tsx  # Full-featured plagiarism scanner UI
├── backend.py                 # FastAPI server (all plagiarism endpoints)
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable reference
└── README.md                  # This file
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
