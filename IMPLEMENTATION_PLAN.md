# COMPREHENSIVE IMPLEMENTATION PLAN
# Ministry-Scale Graduation Project Plagiarism Engine
# Source of Truth: BLUEPRINT.md · DESIGN_SYSTEM.md

> **This plan is the step-by-step execution guide for building the full system.**
> It references BLUEPRINT.md for architecture decisions and DESIGN_SYSTEM.md for UI/UX rules.
> Every task is ordered by dependency. No task should be started before its prerequisites are complete.

---

## PHASE 0: CLEANUP & FOUNDATION
> **Goal:** Remove dead code, establish the Emerald & Butter theme, and set up the project skeleton properly before building any features.

### 0.1 Remove Junk Files from Project Root
**Why:** The root of `plagiarism_engine_scan/` is cluttered with one-off debug/fix scripts that were created during iterative development. They confuse any agent or developer reading the codebase.
**Files to DELETE:**
- `debug_err.py`
- `fix_analysis.py`
- `fix_backend.py`
- `fix_db.py`
- `fix_routes.py`
- `patch_plagiarism.py`
- `patch_ui.py`
- `refactor_backend.py`
- `rewrite_backend.py`
- `test_db.py`

### 0.2 Apply the "Emerald & Butter" Color Theme
**Reference:** `DESIGN_SYSTEM.md` → Section 1 (Color Palette)
**File to modify:** `frontend/src/index.css`
**What to do:**
- Replace current CSS variables (`:root` and `.dark`) with the exact Emerald & Butter palette:
  - Light Mode: background `#faf9f5`, text `#013e37`, primary `#013e37`, accent `#ffefb3`
  - Dark Mode: background `#061a17`, cards `#0c2b26`, primary `#ffefb3`, text `#f4f3ec`
- Replace the current indigo/violet accent (`--accent: 79 70 229`) with the green/butter values.
- Update `.btn-primary` gradient to use Deep Emerald → slightly lighter green.
- Update `.glass-card` and `.glass-panel` border colors to match the warm palette.

### 0.3 Install Font: "Plus Jakarta Sans"
**Reference:** `DESIGN_SYSTEM.md` → Section 2 (Typography)
**What to do:**
- Add `@fontsource/plus-jakarta-sans` to `package.json` dependencies.
- Import it in `main.tsx` or `index.css`.
- Set `font-family: 'Plus Jakarta Sans', sans-serif;` on `html, body`.

### 0.4 Update `App.tsx` with Full Navigation Skeleton
**Reference:** `BLUEPRINT.md` → Section 5 (Decoupled Pages Roadmap)
**What to do:**
- Replace the current inline `NavBar` (which only has Intake and Scanner links) with a proper responsive sidebar or top-nav that includes links for ALL Phase 1 pages:
  - `/` → Project Intake
  - `/scan` → Plagiarism Scanner
  - `/dashboard` → Dashboard
  - `/projects` → Projects
  - `/teams` → Team Management
  - `/users` → User Management
  - `/settings` → Settings
- Add lazy imports and `<Route>` entries for each page.
- Add a placeholder "Login" page at `/login` (no auth logic yet, just the UI shell).

---

## PHASE 1A: BACKEND — COMPLETE THE API LAYER
> **Goal:** The backend currently only serves plagiarism intake/scan. It needs full CRUD APIs for Users, Teams, Projects, Auth, and Dashboard stats.

### 1A.1 Add Authentication & RBAC Middleware
**Reference:** `BLUEPRINT.md` → Section 5 (RBAC)
**What to do:**
- Add a `users` table to `db.py` schema: `id`, `name`, `email`, `password_hash`, `role` (enum: `ministry_admin`, `college_admin`, `student`), `college_id`, `created_at`.
- Add a `students` table: `id`, `enrollment_number` (رقم قيد), `name`, `college_id`, `team_id`.
- Implement JWT-based auth endpoints in `backend.py`:
  - `POST /api/auth/login` → Returns JWT token.
  - `POST /api/auth/register` → Creates a new user (admin-only for staff, student self-register by enrollment number).
  - `GET /api/auth/me` → Returns current user profile from token.
- Create a `require_role()` FastAPI dependency that reads the JWT token and checks the user's role before allowing access to protected endpoints.
- **Password Hashing:** Use `bcrypt` (add to `requirements.txt`).
- **JWT Library:** Use `python-jose[cryptography]` (add to `requirements.txt`).

### 1A.2 Add Teams CRUD API
**Reference:** `BLUEPRINT.md` → Section 6 (Teams entity)
**What to do:**
- Add a `teams` table to `db.py`: `id`, `name`, `college_id`, `created_at`.
- Add endpoints:
  - `GET /api/teams` → List teams (filtered by `college_id` for college admins).
  - `POST /api/teams` → Create a team.
  - `GET /api/teams/{id}` → Get team details + members.
  - `PUT /api/teams/{id}` → Update team name.
  - `DELETE /api/teams/{id}` → Delete team.
  - `POST /api/teams/{id}/members` → Add student to team by enrollment number.
  - `DELETE /api/teams/{id}/members/{student_id}` → Remove student from team.

### 1A.3 Add Users CRUD API
**What to do:**
- Add endpoints:
  - `GET /api/users` → List users (admin-only, filterable by role/college).
  - `POST /api/users` → Create a user (admin-only).
  - `PUT /api/users/{id}` → Update user.
  - `DELETE /api/users/{id}` → Delete user.
  - `GET /api/users/{id}` → Get user profile.

### 1A.4 Expand Projects API
**Reference:** `BLUEPRINT.md` → Section 6 (Projects entity)
**Current state:** `GET /api/plagiarism/projects` returns a simple list with `{id, name}`.
**What to do:**
- Expand the `projects` table schema to include: `title`, `abstract`, `team_id`, `department`, `year`, `university`, `status` (default: "Indexed").
- Expand `GET /api/plagiarism/projects` to return full metadata.
- Add `PUT /api/plagiarism/projects/{id}` → Update project metadata.
- Add `DELETE /api/plagiarism/projects/{id}` → Delete project and its files/fingerprints (cascading delete).
- Add `GET /api/plagiarism/projects/{id}/files` → List files belonging to a project.

### 1A.5 Add Dashboard Stats API
**What to do:**
- Add endpoint: `GET /api/dashboard/stats` → Returns:
  - `total_projects` (COUNT of projects table)
  - `total_teams` (COUNT of teams table)
  - `total_users` (COUNT of users table)
  - `total_files` (COUNT of project_files table)
  - `recent_scans` (last 10 from scan_history.json or a new `scan_reports` table)
  - `flagged_count` (scans where verdict = FLAGGED)

### 1A.6 Add Settings API
**What to do:**
- Add a `settings` table (key-value store): `key VARCHAR PRIMARY KEY`, `value TEXT`.
- Add endpoints:
  - `GET /api/settings` → Returns all settings as a JSON object.
  - `PUT /api/settings` → Bulk update settings (admin-only).
- Default settings: `similarity_threshold` (65), `max_upload_size_mb` (500), `default_language` ("en").

### 1A.7 Wire the Deep AI Scan Endpoint (Hybrid Phase 2 Button)
**Reference:** `BLUEPRINT.md` → Section 2.2 (Deep AI Semantic Analysis)
**What to do:**
- Add endpoint: `POST /api/plagiarism/deep-scan`
  - Accepts: `{ project_id, file1_path, file2_path, other_project_id }`
  - For code files: Loads both files from DB, runs `UniXcoder` (`D:\AI engine\models\unixcoder-base`) cosine similarity.
  - For text files: Loads both files from DB, runs `BGE-M3` (`D:\AI engine\models\bge-m3`) cosine similarity.
  - Returns: `{ ai_similarity: 92.3, model_used: "unixcoder-base", verdict: "CONFIRMED_PLAGIARISM" }`
- The model paths must read from `MODELS_DIR` environment variable (already set in `.env`).

---

## PHASE 1B: FRONTEND — MIGRATE & BUILD ALL PAGES
> **Goal:** Migrate the ready UI pages from the old frontend and wire them to the new backend APIs.

### 1B.1 Migrate `api.ts` (The API Client)
**Source:** `D:\AI engine\frontend\src\lib\api.ts` (982 lines, 31KB)
**Target:** `D:\AI engine\plagiarism_engine_scan\frontend\src\lib\api.ts` (currently 433 lines, 13KB)
**What to do:**
- Merge the old `api.ts` into the new one. The old file contains complete API clients for:
  - `usersApi` (CRUD for users)
  - `teamsApi` (CRUD for teams)
  - `projectsApi` (CRUD for projects with tasks/deliverables)
  - `sessionsApi` (academic sessions)
  - `settingsApi` (user settings)
  - `notificationsApi`
  - `systemHealthApi`
- Keep the new file's `plagiarismApi` (which has the working Winnowing scan endpoints).
- Remove `biometricsApi` (not part of this system).
- Add a new `authApi` section for login/register/me.
- Add a `dashboardApi` section for stats.

### 1B.2 Migrate `i18n.tsx` (Internationalization)
**Source:** `D:\AI engine\frontend\src\lib\i18n.tsx` (38KB — contains Arabic + English translations)
**Target:** `D:\AI engine\plagiarism_engine_scan\frontend\src\lib\i18n.tsx` (currently 3.6KB — minimal)
**What to do:**
- Replace the minimal i18n file with the full Arabic/English translation file from the old frontend.
- Ensure all page strings use `t("key")` for bilingual support.

### 1B.3 Migrate Ready Pages
**Source:** `D:\AI engine\frontend\src\pages\`
**Target:** `D:\AI engine\plagiarism_engine_scan\frontend\src\pages\`
**Pages to migrate (copy, then adapt imports to new api.ts):**

| Old File | New Route | Adaptation Notes |
|---|---|---|
| `Login.tsx` | `/login` | Wire to new `authApi.login()` |
| `Register.tsx` | `/register` | Wire to new `authApi.register()` |
| `CommandCenter.tsx` | `/dashboard` | Rename to `Dashboard.tsx`. Wire to `dashboardApi.getStats()`. Update charts to use Emerald & Butter colors. |
| `Projects.tsx` | `/projects` | Wire to expanded `projectsApi`. Add role-based filtering. |
| `ProjectDetail.tsx` | `/projects/:id` | Wire to `projectsApi.getById()`. |
| `Teams.tsx` | `/teams` | Wire to `teamsApi`. Ensure enrollment number (رقم قيد) field is prominent. |
| `UserManagement.tsx` | `/users` | Wire to `usersApi`. Include AddUser inline or as modal. |
| `AddUser.tsx` | (modal/inline) | Merge into UserManagement page as a slide-over panel. |
| `Settings.tsx` | `/settings` | Wire to `settingsApi`. Add similarity threshold slider. |
| `NotFound.tsx` | `*` | 404 catch-all route. |

**Do NOT migrate:** `Plagiarism.tsx` (old version) — the new `Plagiarism.tsx` and `PlagiarismAnalysis.tsx` already exist and work.

### 1B.4 Fix the Existing Plagiarism Intake Page (`Plagiarism.tsx`)
**File:** `D:\AI engine\plagiarism_engine_scan\frontend\src\pages\Plagiarism.tsx` (105KB!)
**What to do:**
- This file is massively bloated (105KB / ~2000 lines). It contains dead scan result rendering code, old button labels with literal quotes, and stale toast messages.
- Strip out all `scanResult` rendering logic (that now lives in `PlagiarismAnalysis.tsx`).
- Clean up button labels: remove literal quote characters from JSX text.
- Target size after cleanup: ~30-40KB.

### 1B.5 Add "Deep AI Analysis" Button to Scan Results Table
**Reference:** `BLUEPRINT.md` → Section 2.2, `DESIGN_SYSTEM.md` → Section 4.2
**File:** `PlagiarismAnalysis.tsx`
**What to do:**
- In the comparisons table, add a new column: "AI Verify".
- Each row gets a button: "🔬 Deep Scan".
- On click: calls `POST /api/plagiarism/deep-scan` with the two file paths.
- Shows a modal with: AI model name, semantic similarity score, and a verdict badge.

### 1B.6 Restyle ALL Migrated Pages to Emerald & Butter Theme
**Reference:** `DESIGN_SYSTEM.md` → Full document
**What to do:**
- After migration, go through every page and ensure:
  - All hardcoded color classes (e.g., `bg-indigo-600`, `text-violet-500`) are replaced with theme-aware classes (`bg-primary`, `text-accent`, `bg-card`).
  - All cards use `rounded-xl` or `rounded-2xl`.
  - All tables have sticky headers and row hover effects.
  - All buttons have loading spinners during API calls.
  - Dark mode looks like a "Luxury Command Center" (deep green backgrounds, butter accents).

---

## PHASE 1C: DATABASE MIGRATION
> **Goal:** The current database schema is minimal. Add all the tables needed for Phase 1.

### 1C.1 Add New Tables to `db.py`
**What to add to `_init_schema()` (for both PostgreSQL and SQLite modes):**

```sql
-- Users & Auth
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'student',
    college_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Students (linked by enrollment number)
CREATE TABLE IF NOT EXISTS students (
    id VARCHAR(255) PRIMARY KEY,
    enrollment_number VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    college_id VARCHAR(255),
    team_id VARCHAR(255) REFERENCES teams(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teams
CREATE TABLE IF NOT EXISTS teams (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    college_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Settings (key-value)
CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL
);
```

### 1C.2 Expand the `projects` Table
**Add columns via ALTER TABLE (or recreate):**
- `title VARCHAR(500)`
- `abstract TEXT`
- `team_id VARCHAR(255) REFERENCES teams(id)`
- `department VARCHAR(255)`
- `year INTEGER`
- `university VARCHAR(255)`
- `status VARCHAR(50) DEFAULT 'Indexed'`

---

## PHASE 1D: INTEGRATION TESTING & VERIFICATION
> **Goal:** Before declaring Phase 1 complete, verify every endpoint and page works end-to-end.

### 1D.1 Backend Smoke Tests
- Start the backend: `d:\AI engine\.venv\Scripts\uvicorn.exe backend:app --host 0.0.0.0 --port 8000 --reload`
- Test every endpoint manually or via a script:
  - `POST /api/auth/login` with test credentials.
  - `GET /api/dashboard/stats` returns valid counts.
  - `GET /api/teams` returns list.
  - `POST /api/plagiarism/scan` with a known project returns results.
  - `POST /api/plagiarism/deep-scan` with two flagged files returns AI similarity.

### 1D.2 Frontend Smoke Tests
- Start the frontend: `cd frontend && npm run dev`
- Navigate to every page and verify:
  - Login page renders and authenticates.
  - Dashboard shows stats cards and charts.
  - Projects table loads and is filterable.
  - Teams page shows teams with member lists.
  - Intake page uploads a ZIP successfully.
  - Scanner page runs a scan and shows results.
  - Deep Scan button opens modal with AI result.
  - Settings page saves and loads values.
  - Dark mode toggle works with Emerald & Butter colors.
  - RTL (Arabic) mode works via i18n toggle.

### 1D.3 Print-Friendly Report
- Verify that `Ctrl+P` on the Scan Results page produces a clean, printable plagiarism report (the print CSS already exists in `index.css`).

---

## PHASE 2: POST-MVP FEATURES (TO BE PLANNED AFTER PHASE 1 IS STABLE)
> **Reference:** `BLUEPRINT.md` → Section 3

These are documented for completeness but **must not be started until Phase 1 passes all smoke tests:**

### 2.1 Student Semantic "Idea" Search
- Install `pgvector` extension in PostgreSQL.
- Add `abstract_vectors` table with `vector(1024)` column.
- On project intake, compute BGE-M3 embedding of the abstract and store it.
- Build `/idea-search` page with a centered search bar.
- Backend: `POST /api/search/ideas` → Accepts text, computes embedding, queries `pgvector` for top-K similar abstracts.

### 2.2 Faculty Proposal Approval Workflow
- Add `proposals` table: `id`, `student_id`, `title`, `abstract`, `status` (Pending/Approved/Rejected), `reviewed_by`, `reviewed_at`.
- Build `/proposals` page (Kanban or list view).
- Backend CRUD + status transition endpoints.

### 2.3 Side-by-Side Diff Highlighting
- Backend: Add `POST /api/plagiarism/diff` → Accepts two file paths, returns aligned diff with character offsets.
- Frontend: Build a split-pane React component using `react-diff-viewer` or a custom implementation.
- Highlight stolen passages with `bg-red-500/20`.

### 2.4 Institutions Management
- Add `universities` and `departments` tables.
- Build `/institutions` page with nested accordion UI.
- Backend CRUD endpoints.

---

## FILE MAP (Final State After All Phase 1 Tasks)

```
plagiarism_engine_scan/
├── BLUEPRINT.md                    # Architecture source of truth
├── DESIGN_SYSTEM.md                # UI/UX source of truth
├── IMPLEMENTATION_PLAN.md          # This file
├── .env                            # MODELS_DIR path
├── requirements.txt                # Python dependencies (add bcrypt, python-jose)
├── backend.py                      # FastAPI server (all endpoints)
│
├── plagiarism_engine/              # Core Python engine
│   ├── __init__.py
│   ├── db.py                       # PostgreSQL/SQLite schema + queries
│   ├── extractor.py                # File extraction (ZIP, Git, raw)
│   ├── winnowing.py                # Winnowing fingerprinting
│   ├── code_detector.py            # CodeBERT/UniXcoder (for deep scan)
│   ├── text_detector.py            # TF-IDF + cosine similarity
│   ├── vector_store.py             # ChromaDB / embedding store
│   └── minhash_index.py            # MinHash LSH index
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx
│       ├── index.css               # Emerald & Butter theme variables
│       ├── App.tsx                  # Full routing + responsive nav
│       ├── lib/
│       │   ├── api.ts              # Unified API client (merged)
│       │   ├── i18n.tsx            # Full Arabic/English translations
│       │   └── utils.ts
│       └── pages/
│           ├── Login.tsx
│           ├── Register.tsx
│           ├── Dashboard.tsx       # (migrated from CommandCenter.tsx)
│           ├── Plagiarism.tsx      # Intake page (cleaned up)
│           ├── PlagiarismAnalysis.tsx  # Scan page + Deep Scan button
│           ├── Projects.tsx        # (migrated)
│           ├── ProjectDetail.tsx   # (migrated)
│           ├── Teams.tsx           # (migrated)
│           ├── UserManagement.tsx  # (migrated, includes AddUser)
│           ├── Settings.tsx        # (migrated)
│           └── NotFound.tsx        # (migrated)
│
└── data/                           # Runtime data (SQLite fallback, scan history)
    ├── system_db.sqlite
    └── scan_history.json
```

---

## MODELS REFERENCE (Local, Zero-Cost)

All models are pre-downloaded at `D:\AI engine\models\`. No internet downloads needed at runtime.

| Model | Path | Role | Used In |
|---|---|---|---|
| `unixcoder-base` | `D:\AI engine\models\unixcoder-base` | Code clone detection (SOTA on CodeXGLUE) | Deep Scan endpoint |
| `bge-m3` | `D:\AI engine\models\bge-m3` | Multilingual text embeddings (SOTA on MTEB) | Deep Scan + Phase 2 Idea Search |
| `codebert-base` | `D:\AI engine\models\codebert-base` | Legacy code model (superseded by UniXcoder) | Not actively used |
| `codet5p-220m` | `D:\AI engine\models\codet5p-220m` | Code generation model | Not used for plagiarism |
| `arabertv02` | `D:\AI engine\models\arabertv02` | Arabic-specific BERT | Backup for Arabic-only tasks |
| `LaBSE` | `D:\AI engine\models\LaBSE` | Language-Agnostic BERT Sentence Embeddings | Backup multilingual |
| `multilingual-e5-large` | `D:\AI engine\models\multilingual-e5-large` | Multilingual embeddings | Backup (BGE-M3 preferred) |
| `multilingual-e5-base` | `D:\AI engine\models\multilingual-e5-base` | Smaller multilingual | Backup |
| `paraphrase-multilingual-MiniLM-L12-v2` | `D:\AI engine\models\paraphrase-multilingual-MiniLM-L12-v2` | Fast paraphrase detection | Lightweight backup |
| `all-MiniLM-L6-v2` | `D:\AI engine\models\all-MiniLM-L6-v2` | English sentence embeddings | Lightweight English-only |

**Primary models (as per BLUEPRINT.md):** `unixcoder-base` (code) and `bge-m3` (text).

---

## EXECUTION ORDER SUMMARY

```
Phase 0 (Foundation)     →  0.1 Cleanup → 0.2 Theme → 0.3 Font → 0.4 Nav Skeleton
Phase 1A (Backend APIs)  →  1A.1 Auth → 1A.2 Teams → 1A.3 Users → 1A.4 Projects → 1A.5 Dashboard → 1A.6 Settings → 1A.7 Deep Scan
Phase 1B (Frontend)      →  1B.1 api.ts → 1B.2 i18n → 1B.3 Migrate Pages → 1B.4 Fix Intake → 1B.5 Deep Scan UI → 1B.6 Restyle
Phase 1C (Database)      →  1C.1 New Tables → 1C.2 Expand Projects
Phase 1D (Testing)       →  1D.1 Backend Tests → 1D.2 Frontend Tests → 1D.3 Print Report
Phase 2 (Post-MVP)       →  2.1 Idea Search → 2.2 Proposals → 2.3 Diff UI → 2.4 Institutions
```

> **Rule:** Phase 1A and 1C can run in parallel (backend + database). Phase 1B depends on 1A being mostly done. Phase 1D must come last. Phase 2 must not start until Phase 1D passes.
