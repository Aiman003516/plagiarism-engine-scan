# Phase 2 Goal: Codebase Refactoring

## Objective
Split the 3 oversized files into clean, modular files WITHOUT changing any logic or behavior. Refactoring changes WHERE code lives, never WHAT it does.

## Context
Read `MASTER_ROADMAP.md` in this repo for the full project context, architecture, and execution order. This is Phase 2 of 6.

## Tasks

### Task 1: Split `backend.py` (1,826 lines → 10 files)

Create this structure:
```
app/
├── main.py              (~100 lines) — FastAPI app instance, CORS config, startup event, include all routers
├── dependencies.py      (~80 lines)  — JWT_SECRET, JWT auth logic, require_role() dependency, get_db()
├── routers/
│   ├── auth.py           (~200 lines) — POST /api/auth/login, POST /api/auth/change-password, GET /api/auth/me
│   ├── users.py          (~250 lines) — CRUD /api/users, /api/students endpoints
│   ├── projects.py       (~300 lines) — /api/plagiarism/projects/* (list, create, approve, delete)
│   ├── scanner.py        (~400 lines) — /api/plagiarism/upload-scan, upload-scan-stream, git-scan-stream, deep-scan-bulk, scan-stream/{project}
│   ├── settings.py       (~80 lines)  — GET/PUT /api/settings
│   └── dashboard.py      (~50 lines)  — GET /api/dashboard/stats
└── services/
    ├── intake.py          (~200 lines) — _run_intake(), _run_analysis(), _compute_project_similarity()
    └── git_clone.py       (~100 lines) — _clone_git_repo()
```

Rules:
- Each router uses `from fastapi import APIRouter` with appropriate `prefix` and `tags`
- `main.py` imports and includes all routers via `app.include_router()`
- Shared state (db instance, FAISS index, model pool, scan sessions dict) lives in `dependencies.py` or a shared `state.py`
- All existing endpoint paths must remain EXACTLY the same (no URL changes)
- Update `uvicorn` run command at the bottom to point to `app.main:app`

### Task 2: Split `plagiarism_engine/db.py` (1,347 lines → 7 files)

Create this structure:
```
plagiarism_engine/db/
├── __init__.py          — re-export SystemDBStore so all existing imports still work
├── connection.py        (~100 lines) — _get_conn(), connection management
├── schema.py            (~120 lines) — ensure_tables(), all CREATE TABLE statements
├── projects_store.py    (~300 lines) — project and project_files CRUD
├── fingerprint_store.py (~200 lines) — fingerprint batch insert/query/delete
├── users_store.py       (~200 lines) — user + student CRUD
├── teams_store.py       (~150 lines) — team CRUD
└── settings_store.py    (~50 lines)  — get_setting(), put_setting()
```

Rules:
- `SystemDBStore` class is preserved as the public API — it just delegates to the sub-stores
- `__init__.py` exports `SystemDBStore` so `from plagiarism_engine.db import SystemDBStore` still works
- No SQL query changes, no logic changes, just moving methods to their domain files

### Task 3: Split `frontend/src/pages/Plagiarism.tsx` (1,358 lines → 7 files)

Create this structure:
```
frontend/src/pages/plagiarism/
├── index.tsx             (~100 lines) — main page layout, tab/section switching
├── UploadSection.tsx     (~200 lines) — file/zip drag-and-drop upload form
├── GitScanSection.tsx    (~150 lines) — git URL input + provider select + token
├── ScanProgress.tsx      (~200 lines) — SSE progress bar, live log output
├── ResultsSummary.tsx    (~200 lines) — verdict cards, similarity scores
├── ComparisonSection.tsx (~200 lines) — project-vs-project comparison view
└── hooks/
    └── useScanStream.ts  (~150 lines) — EventSource connection, Zustand integration
```

Rules:
- Update the route in `App.tsx` to import from `./pages/plagiarism` (index.tsx)
- Props are passed down or use Zustand store for shared state
- All UI must look and behave EXACTLY the same after splitting

### Task 4: Verify Everything Works

After all splits:
1. Run `cd frontend && npx tsc --noEmit` — must pass with zero errors
2. Start the backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Start the frontend: `cd frontend && npm run dev`
4. Test: login, view dashboard, upload a file, run a scan — all must work
5. Run `git add . && git commit -m "refactor: split backend, db, and Plagiarism into modular files" && git push`

## Success Criteria
- [ ] No file exceeds 400 lines
- [ ] All API endpoints respond identically (same URLs, same responses)
- [ ] Frontend TypeScript compiles with zero errors
- [ ] Backend starts without import errors
- [ ] Git pushed to GitHub
