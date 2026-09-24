# Phase 2 Handoff Blueprint: Plagiarism Engine Scan

> **ATTENTION AI AGENT:** You are taking over a working codebase. The FastAPI backend
> ML pipelines (Winnowing fingerprints, UniXcoder, BGE-M3) and the React 19 + Vite
> frontend exist and are functional. Your job is to execute *surgical* architectural
> upgrades and fix specific state bugs WITHOUT causing "context collapse" — do NOT
> rewrite existing working pipelines, do NOT change the Emerald/Butter design system,
> and do NOT replace working SSE readers or scan logic that already work.
>
> **Execute modules one by one.** Do not move to the next module until the user
> explicitly confirms the current one is tested and working.

### ⛔ Things That Are NOT In Scope
- **SSL/HTTPS** — Both servers run on `localhost`. SSL is a deployment concern (Nginx/Caddy
  reverse proxy), not a code concern. Do NOT add certificate generation or HTTPS config.
- **Replacing SQLite** — FAISS is a *search acceleration layer*, NOT a database replacement.
  SQLite stores file content, metadata, users, teams, and fingerprints. FAISS stores
  only dense vectors + integer IDs for fast nearest-neighbor lookup.
- **Replacing Winnowing** — Winnowing catches structural copy-paste via hash matching.
  FAISS catches semantic similarity via AI embeddings. They serve different purposes
  and both must coexist.
- **Replacing ChromaDB** — `get_vstore()` already exists. FAISS is added alongside it,
  not instead of it.

### Storage Architecture (Do Not Violate)
```
┌─────────────────────────────────────────────────────────────────┐
│ SQLite (system_db.sqlite)         — SOURCE OF TRUTH            │
│   Files, content, metadata, users, teams, fingerprint_index    │
├─────────────────────────────────────────────────────────────────┤
│ Winnowing (fingerprint_index table in SQLite)                  │
│   Hash-based structural fingerprints → catches exact copy      │
├─────────────────────────────────────────────────────────────────┤
│ ChromaDB (chroma_db/)             — existing vector store      │
│   Used by _run_intake() line 237                               │
├─────────────────────────────────────────────────────────────────┤
│ FAISS (NEW — data/faiss_index/)   — fast semantic search       │
│   Dense vectors from UniXcoder/BGE-M3 → sub-50ms search       │
│   Maps integer_id → {project_id, file_path} via JSON sidecar  │
│   Memory: ~3 KB per file (768 dims × float32)                  │
│   10k files = 30 MB RAM, 100k files = 300 MB RAM               │
└─────────────────────────────────────────────────────────────────┘

Upload flow:  SQLite(save) → Winnowing(hash) → ChromaDB(embed) → FAISS(index)
Scan flow:    Winnowing(structural matches) + FAISS(semantic matches) → merged report
```

---

## Codebase Map (Read Before Touching Anything)

```
C:\Users\Ayman\Downloads\plagiarism_engine_scan\
├── backend.py                              # FastAPI app (1233 lines)
│   ├── _run_intake()          (line 199)   # Phase 1: extract → DB → Winnow fingerprints
│   ├── _run_analysis()        (line 296)   # Phase 2: query fingerprint index → comparisons
│   ├── _cosine_similarity()   (line 1137)  # Numpy dot product (FAISS target)
│   ├── _get_deep_scan_model() (line 116)   # Loads SentenceTransformer (UniXcoder / BGE-M3)
│   ├── deep_scan()            (line 1155)  # POST /api/plagiarism/deep-scan
│   ├── upload_zip_stream()    (line 978)   # POST /api/plagiarism/upload-zip-stream (SSE)
│   └── get_db() / get_vstore()             # SQLite DB + ChromaDB vector store singletons
├── plagiarism_engine/
│   ├── db.py                               # SystemDBStore (SQLite/PostgreSQL)
│   │   └── query_candidates() (line 944)   # Fingerprint lookup — returns {file: count}
│   ├── winnowing.py                        # Winnowing fingerprint computation
│   ├── minhash_index.py                    # MinHash LSH alternative index
│   └── extractor.py                        # FileExtractor.scan_project_directory()
├── requirements.txt                        # numpy, sentence-transformers, chromadb, etc.
├── data/
│   ├── system_db.sqlite                    # All projects, files, fingerprints, users
│   ├── chroma_db/                          # ChromaDB vector store (already exists)
│   └── scan_history.json                   # Scan results log
├── frontend/
│   ├── package.json                        # React 19, Vite 6, react-router-dom v7
│   ├── src/
│   │   ├── App.tsx                         # BrowserRouter + <Routes> + Sidebar (187 lines)
│   │   ├── main.tsx                        # ReactDOM.createRoot entry
│   │   ├── lib/
│   │   │   └── api.ts                      # Unified API client (674 lines)
│   │   │       ├── plagiarismApi.uploadAndScanStream()  (line 270)
│   │   │       ├── plagiarismApi.uploadZipStream()      (line 357)
│   │   │       └── plagiarismApi.scanGitRepoStream()    (line 439)
│   │   └── pages/
│   │       ├── Plagiarism.tsx              # Project Intake page (1295 lines) — THE MAIN TARGET
│   │       │   ├── readZipScanStream()     (line 54)  # GPT-6's SSE parser — KEEP THIS
│   │       │   ├── processRawFiles()       (line 211) # Reads File[] → UploadedFileInfo[]
│   │       │   ├── startDirectScan()       (line ~440)# Dispatches ZIP or code-file upload
│   │       │   └── startGitScan()          (line ~522)# Dispatches git clone + scan
│   │       ├── PlagiarismAnalysis.tsx      # Deep scan comparison UI
│   │       ├── Dashboard.tsx, Projects.tsx, Settings.tsx, etc.
```

### Critical Backend Endpoints

| Endpoint | Method | Purpose | Response |
|---|---|---|---|
| `/api/plagiarism/upload-zip-stream` | POST | Upload ZIP, extract, fingerprint, scan | SSE `text/event-stream` |
| `/api/plagiarism/upload-scan-stream` | POST | Upload raw files, fingerprint, scan | SSE `text/event-stream` |
| `/api/plagiarism/git-scan-stream` | POST | Clone git repo, fingerprint, scan | SSE `text/event-stream` |
| `/api/plagiarism/scan` | POST | Run analysis on already-ingested project | JSON |
| `/api/plagiarism/deep-scan` | POST | 1-to-1 AI embedding comparison (UniXcoder/BGE-M3) | JSON |

### Key Architectural Facts
- **No git** — the project has no `.git` directory. There is no version history to fall back on.
- **No Zustand** — the frontend has zero global state management. Everything is local `useState` inside page components.
- The frontend dev server runs on port **3000** (`vite --port=3000`).
- The backend runs on port **8000** via uvicorn.
- The Python virtual environment lives at `D:\AI engine\.venv\`.
- `api.ts` line 292 has a **30-second timeout** on `uploadAndScanStream` — this will kill long uploads silently. Must be raised or removed.

---

## Module 1: React Global State — Fix Component Unmounting

### The Problem
All upload state (`isScanning`, `scanLogs`, `uploadedFiles`, `scanResult`) and the
active SSE `fetch()` request live as local `useState` inside `Plagiarism.tsx`. When
the user navigates to any other page (Dashboard, Settings, etc.) via `react-router-dom`,
React **unmounts** the `Plagiarism` component, which:
1. Destroys all state variables instantly.
2. Aborts the in-flight `fetch()` to the SSE endpoint.
3. When the user navigates back, React mounts a **fresh, empty** Plagiarism component.

### The Solution

#### Step 1: Install Zustand
```bash
cd frontend && npm install zustand
```

#### Step 2: Create the Scan Store
Create a new file: `frontend/src/lib/scanStore.ts`

This store must hold:
```typescript
interface ScanStore {
  // Upload state
  isScanning: boolean;
  scanLogs: string[];
  scanResult: PlagiarismScanResult | null;
  scanError: string | null;
  activeProjectName: string;

  // Actions
  appendLog: (text: string) => void;
  startScan: (projectName: string) => void;
  completeScan: (result: PlagiarismScanResult) => void;
  failScan: (error: string) => void;
  resetScan: () => void;

  // AbortController reference (to cancel on demand, NOT on unmount)
  abortController: AbortController | null;
  setAbortController: (controller: AbortController | null) => void;
}
```

#### Step 3: Refactor Plagiarism.tsx
- Remove local `useState` for `isScanning`, `scanLogs`, and scan results.
- Import and `useStore()` from the Zustand store instead.
- The `startDirectScan()` and `startGitScan()` functions should call store actions.
- The SSE reader (`readZipScanStream`) should write to `store.appendLog()`.
- **DO NOT** delete `readZipScanStream` (lines 54–132). It works correctly. Just wire its `onLog` callback to the store.

#### Step 4: Fix the 30-second Timeout in api.ts
In `frontend/src/lib/api.ts`, line 292:
```typescript
const timeoutId = setTimeout(() => controller.abort(), 30000);
```
Change `30000` to `600000` (10 minutes) or remove the timeout entirely for streaming endpoints.

### Files to Modify
| File | Action |
|---|---|
| `frontend/src/lib/scanStore.ts` | **[NEW]** Zustand store |
| `frontend/src/pages/Plagiarism.tsx` | **[MODIFY]** Replace local scan state with store subscriptions |
| `frontend/src/lib/api.ts` | **[MODIFY]** Fix 30s timeout on line 292 |
| `frontend/package.json` | **[MODIFY]** Add `zustand` dependency |

### Acceptance Criteria
1. Start a ZIP upload scan on the Intake page.
2. While the SSE terminal is streaming logs, click "Dashboard" in the sidebar.
3. Wait 5 seconds, then click "Project Intake" in the sidebar.
4. **Expected:** The terminal logs are still streaming. No data was lost.

### DO NOT
- Do not move `processRawFiles()` or `handleDrop()` into the store — those are UI-only concerns.
- Do not delete or rewrite `readZipScanStream()` (lines 54–132 of Plagiarism.tsx).
- Do not change the backend.

---

## Module 2: UI Restoration & Dual-Mode Intake

### The Problem
Previous AI interventions broke the folder upload flow. Currently the Dropzone only
supports ZIP archive uploads. The "Browse Folders" button (using `webkitdirectory`)
was accidentally deleted. Users need BOTH options.

### The Solution

#### Step 1: Add a Hidden Folder Input
In `Plagiarism.tsx`, alongside the existing hidden inputs (`fileInputRef`, `zipInputRef`),
add a third:
```tsx
const folderInputRef = useRef<HTMLInputElement>(null);

// In JSX:
<input
  type="file"
  ref={folderInputRef}
  onChange={handleFolderSelect}
  // @ts-ignore
  webkitdirectory=""
  directory=""
  multiple
  className="hidden"
/>
```

#### Step 2: Add handleFolderSelect Handler
```typescript
const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
  if (e.target.files && e.target.files.length > 0) {
    processRawFiles(Array.from(e.target.files));
    e.target.value = "";
  }
};
```

#### Step 3: Add the "Browse Folders" Button
Inside the Dropzone's quick-action button group (look for `onClick={(e) => e.stopPropagation()}`),
add a button that triggers `folderInputRef.current?.click()` with a `FolderPlus` icon
from `lucide-react`. Import `FolderPlus` in the lucide import block at the top of the file.

#### Step 4: Fix the Dropzone's Default Click
The main Dropzone `onClick` should open the folder picker (most common use case),
not the ZIP picker. Change:
```tsx
onClick={... () => zipInputRef.current?.click()}
```
to:
```tsx
onClick={... () => folderInputRef.current?.click()}
```

### Files to Modify
| File | Action |
|---|---|
| `frontend/src/pages/Plagiarism.tsx` | **[MODIFY]** Add folder input, handler, button, fix dropzone click |

### Acceptance Criteria
1. "Browse Folders" button opens a native folder picker dialog.
2. "Browse Archives" button opens a file picker filtered to `.zip`.
3. Clicking the main Dropzone area opens the folder picker.
4. Drag-and-drop still works for both folders and ZIP files.
5. The SSE terminal UI is fully intact and unchanged.

### DO NOT
- Do not restructure the component layout or change CSS class names.
- Do not touch `readZipScanStream()`.
- Do not touch `startDirectScan()` — it already has the `if (zipFile)` branch that correctly dispatches to `upload-zip-stream`.

---

## Module 3: FAISS Vector Search Optimization (Backend)

### The Problem
The `/api/plagiarism/deep-scan` endpoint (line 1155 of `backend.py`) currently:
1. Loads two files from the database.
2. Encodes both with `SentenceTransformer` (UniXcoder for code, BGE-M3 for text).
3. Computes cosine similarity via `_cosine_similarity()` (line 1137) using raw `numpy`.

This is a **1-to-1 pair comparison**. It works, but it cannot scale to "compare this
file against every file in the entire database" without $O(N)$ sequential encoding and
dot products.

Additionally, the main scan pipeline `_run_analysis()` (line 296) uses **Winnowing
fingerprint hashing** via `db.query_candidates()` (SQL `IN` clause on `fingerprint_index`
table). This is already reasonably fast for hash-based candidate retrieval, but becomes
a bottleneck when the fingerprint table grows to millions of rows.

### The Solution

#### Step 1: Install faiss-cpu
Add to `requirements.txt`:
```
faiss-cpu>=1.7.4
```
Install: `pip install faiss-cpu`

#### Step 2: Create a FAISS Index Manager
Create a new file: `plagiarism_engine/faiss_index.py`

```python
import faiss
import numpy as np
import json
from pathlib import Path

class FAISSIndexManager:
    """Manages a persistent FAISS index for code/text embeddings."""

    def __init__(self, index_dir: str, dimension: int = 768):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self._code_index = None   # faiss.IndexFlatIP for code embeddings
        self._text_index = None   # faiss.IndexFlatIP for text embeddings
        self._id_map = {}         # int_id -> {"project_id": ..., "file_path": ...}

    def add_embeddings(self, embeddings: np.ndarray, metadata: list[dict], domain: str):
        """Add normalized embeddings to the appropriate index."""
        ...

    def search(self, query_embedding: np.ndarray, domain: str, k: int = 10):
        """Return top-k most similar items from the index."""
        ...

    def save(self):
        """Persist index + ID map to disk."""
        ...

    def load(self):
        """Load index + ID map from disk."""
        ...
```

#### Step 3: Integrate into the Intake Pipeline
In `backend.py`, inside `_run_intake()` (line 199), after Winnowing fingerprints are
computed and stored (line 269–275), add a new phase:
```python
log("[PHASE 4/4] 🧠 Computing semantic embeddings for FAISS index...")
# Encode all code files with UniXcoder, all text files with BGE-M3
# Normalize embeddings and add to the FAISS index
```

#### Step 4: Upgrade Deep Scan to Use FAISS
In `backend.py`, enhance the `/api/plagiarism/deep-scan` endpoint (line 1155) to:
1. Encode the source file.
2. Query the FAISS index: `faiss_index.search(embedding, domain="code", k=10)`.
3. Return the top-k most similar files across the **entire database** — not just one pair.

#### Step 5: (Optional) Add FAISS-Accelerated Bulk Scan
Create a new endpoint:
```python
@app.post("/api/plagiarism/deep-scan-bulk")
```
That takes a `project_id`, encodes all its files, and batch-queries FAISS to find
the most similar files across the entire corpus in one shot.

### Files to Modify
| File | Action |
|---|---|
| `plagiarism_engine/faiss_index.py` | **[NEW]** FAISS index manager class |
| `backend.py` | **[MODIFY]** Add FAISS index singleton, integrate into `_run_intake()` and `deep_scan()` |
| `requirements.txt` | **[MODIFY]** Add `faiss-cpu>=1.7.4` |

### Acceptance Criteria
1. After uploading a project, its embeddings are indexed in FAISS.
2. The deep scan endpoint returns results using FAISS search instead of manual numpy.
3. The existing Winnowing fingerprint pipeline (`_run_analysis`) is **untouched** — FAISS is an *addition*, not a replacement.
4. The FAISS index persists to disk (survives server restarts).

### DO NOT
- Do not delete or replace the Winnowing pipeline. It serves a different purpose (structural hash matching vs semantic similarity).
- Do not delete `_cosine_similarity()` — keep it as a fallback.
- Do not change any frontend code in this module.
- Do not remove the ChromaDB vector store (`get_vstore()`) — it may be used elsewhere.

---

## Module 4: SSE Stream Reliability (Backend Fix)

### The Problem
The `upload_zip_stream()` endpoint (line 978 of `backend.py`) has a subtle bug: it
**buffers all logs** in a `logs = []` list, runs the entire intake synchronously via
`run_in_executor()`, and only THEN yields the log messages. This means the user sees
nothing in the terminal until the entire scan is finished — defeating the purpose of SSE.

### The Solution
Refactor the endpoint to yield log messages **as they are produced** using an
`asyncio.Queue`:

```python
@app.post("/api/plagiarism/upload-zip-stream")
async def upload_zip_stream(...):
    log_queue = asyncio.Queue()

    def log_callback(msg: str):
        log_queue.put_nowait(msg)

    async def run_scan_in_background():
        # Run _run_intake in executor, passing log_callback
        # Put a sentinel when done
        ...

    async def event_stream():
        task = asyncio.create_task(run_scan_in_background())
        while True:
            msg = await log_queue.get()
            if msg is SENTINEL:
                break
            yield f"data: {json.dumps({'type': 'log', 'text': msg})}\n\n"
        # Yield final result
        ...

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### Files to Modify
| File | Action |
|---|---|
| `backend.py` | **[MODIFY]** Refactor `upload_zip_stream()` (line 978) and similarly `upload_scan_stream()` and `git_scan_stream()` to use `asyncio.Queue` for real-time log yielding |

### Acceptance Criteria
1. Upload a ZIP file.
2. Logs appear in the frontend terminal **line by line in real time** as the backend processes.
3. The final `complete` event still arrives correctly after all logs.

---

## Module 5: Project-to-Project Comparison Mode (Backend + Frontend)

### The Problem
The system currently supports two comparison modes:
- **Project vs ALL** — `_run_analysis()` scans against every project in the database (Winnowing only)
- **File vs File** — `/api/plagiarism/deep-scan` compares exactly two files (AI embeddings)

**Missing:** There is no way to compare **Project X against specifically Project Y**.
This is the most common use case for professors: *"I suspect Student A copied from
Student B — compare just these two submissions."*

### The Solution

#### Step 1: New Backend Endpoint
Add to `backend.py`:
```python
class CompareProjectsRequest(BaseModel):
    project_x: str          # Source project name/ID
    project_y: str          # Target project name/ID
    use_ai: bool = False    # If True, also run AI embedding comparison (slower)

@app.post("/api/plagiarism/compare-projects")
async def compare_projects(req: CompareProjectsRequest):
    """Compare all files in Project X against all files in Project Y."""
    db = get_db()

    files_x = db.get_project_files(req.project_x)
    files_y = db.get_project_files(req.project_y)

    if not files_x:
        raise HTTPException(404, f"Project '{req.project_x}' not found")
    if not files_y:
        raise HTTPException(404, f"Project '{req.project_y}' not found")

    comparisons = []

    # --- Winnowing comparison (fast, structural) ---
    fps_x = db.get_project_fingerprints(req.project_x)
    fps_y = db.get_project_fingerprints(req.project_y)

    for file_x_path, hashes_x in fps_x.items():
        hash_set_x = set(h for h, _ in hashes_x)
        total_x = len(hash_set_x)
        if total_x == 0:
            continue
        for file_y_path, hashes_y in fps_y.items():
            hash_set_y = set(h for h, _ in hashes_y)
            shared = len(hash_set_x & hash_set_y)
            if shared >= 3 or (shared / total_x) > 0.05:
                sim = shared / total_x
                comparisons.append({
                    "file_x": file_x_path,
                    "file_y": file_y_path,
                    "similarity": round(sim * 100, 2),
                    "shared_fingerprints": shared,
                    "method": "winnowing",
                    "status": "FLAGGED" if sim >= 0.65 else "Moderate" if sim >= 0.25 else "Low"
                })

    # --- Optional: AI embedding comparison for top matches ---
    if req.use_ai:
        # For the top N Winnowing matches, run deep scan to confirm/refine
        pass  # Implement after FAISS is integrated (Module 3)

    comparisons.sort(key=lambda c: c["similarity"], reverse=True)
    overall = comparisons[0]["similarity"] if comparisons else 0.0

    return {
        "project_x": req.project_x,
        "project_y": req.project_y,
        "overall_similarity": overall,
        "verdict": "FLAGGED" if overall >= 65 else "SAFE",
        "total_comparisons": len(comparisons),
        "comparisons": comparisons[:50],
    }
```

#### Step 2: Add to Frontend API Client
In `frontend/src/lib/api.ts`, add to the `plagiarismApi` object:
```typescript
compareProjects: (projectX: string, projectY: string, useAi = false) =>
    apiFetch<any>("/api/plagiarism/compare-projects", {
        method: "POST",
        body: JSON.stringify({ project_x: projectX, project_y: projectY, use_ai: useAi }),
    }),
```

#### Step 3: Add Comparison UI
On `PlagiarismAnalysis.tsx` (or a new page), add:
- Dropdown A: Select Project X (from `plagiarismApi.getProjects()`)
- Dropdown B: Select Project Y
- Button: "Compare Projects"
- Results table: File pairs sorted by similarity with status badges

### Files to Modify
| File | Action |
|---|---|
| `backend.py` | **[MODIFY]** Add `CompareProjectsRequest` model and `/api/plagiarism/compare-projects` endpoint |
| `frontend/src/lib/api.ts` | **[MODIFY]** Add `compareProjects()` to `plagiarismApi` |
| `frontend/src/pages/PlagiarismAnalysis.tsx` | **[MODIFY]** Add project-vs-project comparison UI |

### Acceptance Criteria
1. Upload two separate projects.
2. Call `/api/plagiarism/compare-projects` with both names → get file-pair similarity list.
3. The UI shows two project dropdowns, a compare button, and a sorted results table.

### DO NOT
- Do not modify `_run_analysis()` — it handles "Project vs ALL" and must remain unchanged.
- Do not modify `/api/plagiarism/deep-scan` — it handles "File vs File" and must remain unchanged.
- This is a **new, additive** endpoint.

---

## Execution Order

```
Module 1 (Zustand Global State)
    └── Module 2 (Dual-Mode Intake UI)
        └── Module 4 (SSE Stream Reliability)
            └── Module 3 (FAISS Integration)
                └── Module 5 (Project-to-Project Comparison)
```

> **Rule:** Complete and test each module before starting the next.
> After each module, tell the user what you changed and ask them to test it.

