# CLINE PROMPT — Plagiarism Engine Phase 2 Surgery Guide

> **FOR AI AGENT (DeepSeek V4 / Claude Opus 4.6 / GPT-6):**
> You are fixing a **working but flawed** codebase. The FastAPI backend ML pipelines
> and React 19 frontend exist and function. You must fix bugs and add features
> **surgically** — one module at a time. After each module, STOP and tell the user
> to test manually before you continue.
>
> **CRITICAL RULES:**
> - Do NOT rewrite entire files. Make targeted edits.
> - Do NOT delete working code without explicit instructions.
> - Do NOT add SSL/HTTPS. Both servers run on localhost.
> - Do NOT replace SQLite, ChromaDB, or Winnowing with FAISS. FAISS is additive.
> - Read the "Files to Read" list FIRST before writing any code.

---

## Project Layout

```
C:\Users\Ayman\Downloads\plagiarism_engine_scan\
├── backend.py                              # FastAPI app (1233 lines)
├── plagiarism_engine/
│   ├── db.py                               # SystemDBStore (SQLite/PostgreSQL)
│   ├── winnowing.py                        # Winnowing fingerprint engine
│   ├── minhash_index.py                    # MinHash LSH index
│   ├── extractor.py                        # FileExtractor
│   └── vector_store.py                     # ChromaDB vector store
├── data/
│   ├── system_db.sqlite                    # Main database
│   ├── chroma_db/                          # ChromaDB embeddings
│   └── scan_history.json                   # Scan history
├── requirements.txt                        # Python dependencies
├── frontend/
│   ├── package.json                        # React 19, Vite 6
│   └── src/
│       ├── App.tsx                         # Router + Sidebar (187 lines)
│       ├── main.tsx                        # Entry point
│       ├── lib/
│       │   ├── api.ts                      # API client (674 lines)
│       │   └── i18n.tsx                    # Translations
│       └── pages/
│           ├── Plagiarism.tsx              # Project Intake (1295 lines)
│           ├── PlagiarismAnalysis.tsx       # Scanner/Analysis (327 lines)
│           ├── Dashboard.tsx
│           ├── Projects.tsx
│           ├── Settings.tsx
│           ├── Teams.tsx, Users.tsx, Login.tsx, Register.tsx
```

**Runtime:**
- Backend: `uvicorn backend:app --port 8000` (Python venv at `D:\AI engine\.venv\`)
- Frontend: `npm run dev` → `http://localhost:3000` (Vite on port 3000)

---

# MODULE 1: Frontend Global State (Fix Component Unmounting)

## The Problem
Over 25 `useState` hooks live locally inside `Plagiarism.tsx` (lines 140–180). When
the user navigates to Dashboard/Settings/etc., React unmounts the component, destroying:
- All staged files and bloat-filtration stats
- The active SSE fetch connection
- All scan logs and results
- The scan progress state

## Files to Read First
- `frontend/src/pages/Plagiarism.tsx` lines 140–180 (all useState declarations)
- `frontend/src/App.tsx` lines 147–186 (router structure — no providers exist)
- `frontend/src/lib/api.ts` lines 270–355 (uploadAndScanStream)

## What to Do

### 1.1 Install Zustand
```bash
cd frontend && npm install zustand
```

### 1.2 Create `frontend/src/lib/scanStore.ts`
Move these states out of `Plagiarism.tsx` into a Zustand store.

**IMPORTANT:** There are TWO groups of state that must survive navigation:

**Group A — Pre-scan state (after upload, before clicking Index):**
- `uploadedFiles` — the staged files array (UploadedFileInfo[])
- `projectName` — user-entered or auto-detected project name
- `isProcessingFiles` — whether file content is being read
- `isTraversing` — whether directory structure is being scanned
- `totalFilesToProcess` / `processedFilesCount` — progress bar numbers
- `processingPhase` — current phase label ("Scanning directory structure", "Reading file content", etc.)
- `bloatFilteredCount` / `inspectedTotalNodes` — bloat elimination stats

**Group B — Scan execution state (after clicking Index):**
- `isScanning` — whether SSE scan is active
- `scanLogs` — terminal log lines
- `scanResult` — the final result object
- `scanError` — error message if scan failed

```typescript
import { create } from 'zustand';

interface UploadedFileInfo {
  id: string;
  path: string;
  name: string;
  size: number;
  type: "code" | "text" | "archive" | "other";
  content?: string;
  file: File;
}

interface ScanStore {
  // --- Group A: Pre-scan / Upload state (survives navigation) ---
  uploadedFiles: UploadedFileInfo[];
  projectName: string;
  isProcessingFiles: boolean;
  isTraversing: boolean;
  totalFilesToProcess: number;
  processedFilesCount: number;
  processingPhase: string;
  bloatFilteredCount: number;
  inspectedTotalNodes: number;

  // --- Group B: Scan execution state (survives navigation) ---
  isScanning: boolean;
  scanLogs: string[];
  scanResult: any | null;
  scanError: string | null;

  // --- Actions ---
  setUploadedFiles: (files: UploadedFileInfo[] | ((prev: UploadedFileInfo[]) => UploadedFileInfo[])) => void;
  setProjectName: (name: string) => void;
  setProcessingState: (state: { isProcessing?: boolean; isTraversing?: boolean; total?: number; processed?: number; phase?: string }) => void;
  setBloatStats: (filtered: number, totalNodes: number) => void;
  appendLog: (text: string) => void;
  startScan: (projectName: string) => void;
  completeScan: (result: any) => void;
  failScan: (error: string) => void;
  resetScan: () => void;
  resetAll: () => void;

  // AbortController (to cancel on demand, NOT on unmount)
  abortController: AbortController | null;
  setAbortController: (c: AbortController | null) => void;
}

export const useScanStore = create<ScanStore>((set) => ({
  // Group A defaults
  uploadedFiles: [],
  projectName: '',
  isProcessingFiles: false,
  isTraversing: false,
  totalFilesToProcess: 0,
  processedFilesCount: 0,
  processingPhase: '',
  bloatFilteredCount: 0,
  inspectedTotalNodes: 0,

  // Group B defaults
  isScanning: false,
  scanLogs: [],
  scanResult: null,
  scanError: null,
  abortController: null,

  // Group A actions
  setUploadedFiles: (files) => set((s) => ({
    uploadedFiles: typeof files === 'function' ? files(s.uploadedFiles) : files
  })),
  setProjectName: (name) => set({ projectName: name }),
  setProcessingState: (state) => set((s) => ({
    isProcessingFiles: state.isProcessing ?? s.isProcessingFiles,
    isTraversing: state.isTraversing ?? s.isTraversing,
    totalFilesToProcess: state.total ?? s.totalFilesToProcess,
    processedFilesCount: state.processed ?? s.processedFilesCount,
    processingPhase: state.phase ?? s.processingPhase,
  })),
  setBloatStats: (filtered, totalNodes) => set({ bloatFilteredCount: filtered, inspectedTotalNodes: totalNodes }),

  // Group B actions
  appendLog: (text) => set((s) => ({ scanLogs: [...s.scanLogs, text] })),
  startScan: (name) => set({ isScanning: true, scanLogs: [], scanResult: null, scanError: null, projectName: name }),
  completeScan: (result) => set({ isScanning: false, scanResult: result }),
  failScan: (error) => set({ isScanning: false, scanError: error }),
  resetScan: () => set({ isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null }),
  resetAll: () => set({
    uploadedFiles: [], projectName: '', isProcessingFiles: false, isTraversing: false,
    totalFilesToProcess: 0, processedFilesCount: 0, processingPhase: '',
    bloatFilteredCount: 0, inspectedTotalNodes: 0,
    isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null,
  }),
  setAbortController: (c) => set({ abortController: c }),
}));
```

### 1.3 Refactor `Plagiarism.tsx`
- Remove these local `useState` hooks and use `useScanStore` instead:
  - `projectName` / `setProjectName` (line 145)
  - `uploadedFiles` / `setUploadedFiles` (line 146)
  - `isProcessingFiles` / `setIsProcessingFiles` (line 148)
  - `isTraversing` / `setIsTraversing` (line 149)
  - `totalFilesToProcess` / `setTotalFilesToProcess` (line 150)
  - `processedFilesCount` / `setProcessedFilesCount` (line 151)
  - `processingPhase` / `setProcessingPhase` (line 152)
  - `bloatFilteredCount` / `setBloatFilteredCount` (line 155)
  - `inspectedTotalNodes` / `setInspectedTotalNodes` (line 156)
  - `isScanning` / `scanLogs` — lines 170–171 already use the store, keep them.
- **KEEP as local useState** (these are pure UI state, no need to survive navigation):
  - `activeTab` (line 142) — which tab is selected
  - `isDragging` (line 147) — drag visual indicator
  - `showExplorer`, `stagedSearch`, `stagedCategory` (lines 165–167) — explorer filter UI
  - `terminalAutoScroll`, `lastLogTimestamp`, `timeSinceLastLog` (lines 172–174)
  - `isHistoryOpen`, `historyList`, `isLoadingHistory`, `historySearch` (lines 177–180)
  - All git-related state (lines 159–162) — unless git scan also needs persistence

### 1.4 Fix the 30-second Timeout in `api.ts`
Line 292: `setTimeout(() => controller.abort(), 30000)` — change to `600000` (10 min).
Line 31: `setTimeout(() => timeoutController.abort(), 120000)` — change to `600000` (10 min).

### 1.5 Add a Cancel Scan Button
In `Plagiarism.tsx`, when `isScanning` is true, show a cancel button that calls:
```typescript
const cancel = useScanStore.getState().abortController;
if (cancel) cancel.abort();
useScanStore.getState().resetScan();
```

## Test Manually
1. Start the backend: `& 'D:\AI engine\.venv\Scripts\uvicorn.exe' backend:app --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:3000`
4. Upload a ZIP file on the Intake page. While scanning, click "Dashboard" in the sidebar.
5. Wait 5 seconds. Click "Project Intake" again.
6. **PASS:** Logs are still streaming. No data lost.
7. Test the Cancel button — it should abort the scan cleanly.

---

# MODULE 2: Fix Frontend Upload & Intake Bugs

## The Problem (Multiple Bugs)

### Bug 2A: ZIP upload uses relative URL, bypasses API_BASE_URL
Line 490 of `Plagiarism.tsx`: `fetch("/api/plagiarism/upload-zip-stream")` uses a
relative path. The frontend runs on `localhost:3000` but the backend is on `localhost:8000`.
Without a Vite proxy, this hits Vite and returns a 404 HTML page.

### Bug 2B: ZIP upload missing auth token
Line 490: The `fetch()` does not include `Authorization: Bearer ${token}` header.

### Bug 2C: Scan results are completely discarded
`readZipScanStream` (line 89–90) sets `completed = true` on the `complete` event
but **never extracts `event.result`**. The backend sends `{"type":"complete","result":{...}}`
with all similarity data — it's thrown away. The `onComplete()` callback (line 457) also
ignores its argument.

### Bug 2D: Duplicate project check is broken
Line 474–480: The backend returns a raw `string[]` array, but the frontend checks for
`data.exists` or `data.existing_projects` — properties that don't exist on an Array.
The check always evaluates to false.

### Bug 2E: No project name input field
There is no `<input>` for `projectName` in the Direct Upload tab. The name is auto-guessed
from directory roots or falls back to `"Intake_Project"`.

### Bug 2F: Missing folder upload (webkitdirectory)
No hidden input with `webkitdirectory`. No "Browse Folders" button.

### Bug 2G: History "Inspect" button does nothing
Line 1261–1271: Clicking "Inspect" only fires a toast and closes the modal.
It doesn't fetch the report or navigate to `/scan`.

## Files to Read First
- `frontend/src/pages/Plagiarism.tsx` lines 54–132 (readZipScanStream), 454–520 (startDirectScan), 622–636 (hidden inputs), 760–778 (buttons), 1261–1271 (history inspect)
- `frontend/src/lib/api.ts` lines 244–245 (checkProjectExists return type), 357–431 (uploadZipStream)
- `backend.py` lines 896–904 (check endpoint), 978–1027 (upload-zip-stream)

## What to Do

### 2.1 Fix ZIP Upload URL + Auth (Bug 2A & 2B)
In `startDirectScan`, replace the raw `fetch()` with the existing `plagiarismApi.uploadZipStream()` from `api.ts` (lines 357–431). It already handles `API_BASE_URL` and auth tokens correctly:
```typescript
await plagiarismApi.uploadZipStream(
  activeProjectName,
  zipFile.file,
  (text) => appendLog(text),        // onLog
  (result) => { /* handle result */ onComplete(); },  // onComplete with result
  (msg) => onError(msg)             // onError
);
```
Then **delete** the duplicate `readZipScanStream` function (lines 54–132). It's redundant.

### 2.2 Fix Result Capture (Bug 2C)
Update `onComplete` to accept and store the result:
```typescript
const onComplete = (result?: any) => {
  if (result) {
    useScanStore.getState().completeScan(result);
  }
  appendLog(`[COMPLETED] ✅ Scan completed for ${activeProjectName}.`);
  toast.success(t("intake_progress_title") + " ✓");
};
```

### 2.3 Fix Duplicate Check (Bug 2D)
Line 477: Change from:
```typescript
if (data.exists || (data.existing_projects && data.existing_projects.length > 0))
```
to:
```typescript
if (Array.isArray(data) && data.length > 0)
```

### 2.4 Add Project Name Input (Bug 2E)
Before the Dropzone in the Direct Upload tab, add:
```tsx
<input
  type="text"
  value={projectName}
  onChange={(e) => setProjectName(e.target.value)}
  placeholder={t("project_name_placeholder", "Enter project name (optional)")}
  className="w-full px-4 py-2.5 rounded-xl bg-surface border border-glass-border ..."
/>
```

### 2.5 Add Folder Upload (Bug 2F)
Add `folderInputRef`, a hidden `<input webkitdirectory>`, `handleFolderSelect`, and a
"Browse Folders" button with `FolderPlus` icon (import from `lucide-react`).
Change the Dropzone `onClick` to open `folderInputRef` instead of `zipInputRef`.

### 2.6 Fix History Inspect (Bug 2G)
Replace the dummy toast with:
```typescript
onClick={async () => {
  setIsHistoryOpen(false);
  const detail = await plagiarismApi.getHistoryDetail(h.id);
  useScanStore.getState().completeScan(detail);
  // Navigate to /scan or show inline
}}
```

## Test Manually
1. Open `http://localhost:3000`.
2. Type a project name in the new input field.
3. Click "Browse Folders" — a folder picker opens.
4. Click "Browse Archives" — a `.zip` picker opens.
5. Upload a ZIP file. Watch the terminal for real-time logs.
6. When scan completes, verify the result data is displayed (similarity %, verdict).
7. Open Scan History. Click "Inspect" on a past scan. Verify it loads the report.

---

# MODULE 3: Backend SSE Streaming Fix (Real-Time Logs)

## The Problem
ALL THREE SSE endpoints buffer logs and burst-flush them at the end:
- `upload-scan-stream` (lines 929–975)
- `upload-zip-stream` (lines 978–1027)
- `git-scan-stream` (lines 1049–1096)

Additionally, `git-scan-stream` calls `_clone_git_repo` **synchronously on the main
event loop** (line 1060), freezing the ENTIRE FastAPI server for up to 120 seconds.

## Files to Read First
- `backend.py` lines 929–1096 (all three SSE endpoints)
- `backend.py` lines 419–470 (_clone_git_repo — synchronous subprocess.run)

## What to Do

### 3.1 Refactor All Three SSE Endpoints to Use `asyncio.Queue`
Replace the `logs = []` + post-loop flush pattern with:
```python
import asyncio

@app.post("/api/plagiarism/upload-zip-stream")
async def upload_zip_stream(
    project_name: str = Form(...),
    scan_type: str = Form("ZIP Archive Scan"),
    file: UploadFile = File(...),
):
    import zipfile

    log_queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def run_in_background():
        try:
            # ... extraction logic (same as current) ...
            def log_cb(msg):
                log_queue.put_nowait(msg)

            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _run_intake(project_name, extracted_files, log_callback=log_cb)
            )
            await log_queue.put(("complete", result))
        except Exception as e:
            await log_queue.put(("error", str(e)))
        finally:
            await log_queue.put(SENTINEL)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def event_stream():
        task = asyncio.create_task(run_in_background())
        while True:
            item = await log_queue.get()
            if item is SENTINEL:
                break
            if isinstance(item, tuple):
                typ, payload = item
                if typ == "complete":
                    yield f"data: {json.dumps({'type':'complete','result':payload}, default=str)}\n\n"
                elif typ == "error":
                    yield f"data: {json.dumps({'type':'error','message':payload})}\n\n"
            else:
                yield f"data: {json.dumps({'type':'log','text':item})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### 3.2 Fix `git-scan-stream` Event Loop Blocking
Wrap `_clone_git_repo` in `run_in_executor`:
```python
tmp_dir, git_metadata = await asyncio.get_event_loop().run_in_executor(
    None, lambda: _clone_git_repo(payload.repo_url, payload.branch or "main",
                                   payload.access_token, log_callback=log_callback)
)
```

### 3.3 Fix Orphaned Temp Directories in `_clone_git_repo`
Add `try...finally` cleanup:
```python
def _clone_git_repo(repo_url, branch="main", access_token=None, log_callback=None):
    tmp_dir = tempfile.mkdtemp(prefix="plagiarism_git_")
    try:
        # ... clone logic ...
        return tmp_dir, git_metadata
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
```

### 3.4 Handle `subprocess.TimeoutExpired`
In `_clone_git_repo` (line 441), add catch:
```python
except subprocess.TimeoutExpired:
    raise HTTPException(408, "Git clone timed out after 120 seconds.")
```

## Test Manually
1. Upload a large ZIP file (or a ZIP with many files).
2. Watch the terminal in the frontend.
3. **PASS:** Logs appear ONE BY ONE in real time, not as a burst at the end.
4. Test git scan — the server should remain responsive to other requests during clone.

---

# MODULE 4: Backend Critical Bug Fixes

## Files to Read First
- `backend.py` lines 64–75 (model preloading), 111 (hardcoded path), 163–177 (history)
- `backend.py` lines 296–414 (_run_analysis), 1118 (inverted scans), 1130–1220 (deep scan)
- `plagiarism_engine/db.py` lines 940–981 (query_candidates, store_fingerprints)

## What to Do

### 4.1 Fix Silent History Wipe (CRITICAL)
`_load_history()` line 173: `except Exception: return []` silently wipes history on any
read error. Then `_save_history()` overwrites with just 1 scan. Fix:
```python
def _load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            # Create a backup instead of silently wiping
            backup = HISTORY_FILE.with_suffix(f".backup_{int(time.time())}.json")
            shutil.copy2(HISTORY_FILE, backup)
            return []
    return []
```

### 4.2 Fix Inverted Recent Scans
Line 1118: `history[-10:]` returns the 10 OLDEST scans because `history.insert(0, result)`
prepends new scans at index 0. Fix:
```python
recent_scans = history[:10] if history else []
```

### 4.3 Fix Deep Scan Event Loop Blocking
`deep_scan()` (line 1156) calls `model.encode()` synchronously. Wrap it:
```python
embeddings = await asyncio.get_event_loop().run_in_executor(
    None, lambda: model.encode([content1, content2], convert_to_numpy=True, normalize_embeddings=True)
)
```

### 4.4 Fix Deep Scan Loading Entire Projects for 2 Files
Lines 1160–1164 load ALL files of BOTH projects just to find 2 files. Add a
`get_single_file(project_id, file_path)` method to `db.py` and use it instead.

### 4.5 Fix Deep Scan FileNotFoundError → 500
Lines 1204–1205: `except FileNotFoundError: raise` — this crashes with a raw 500.
Change to:
```python
except FileNotFoundError as e:
    raise HTTPException(status_code=503, detail=f"Model not found: {e}")
```

### 4.6 Fix Model Preload Silent Failure
Lines 64–75: `except Exception: pass` swallows model load failures and sets
`_models_ready = True`. Fix: log the error and set `_models_ready = False`:
```python
except Exception as e:
    import logging
    logging.warning(f"Model preloading failed: {e}")
    _models_ready = False
```

### 4.7 Fix Asymmetric Similarity Metric
Line 358: `sim_val = count / total_fps` is one-directional. A 5-line file matching a
5000-line library scores 100%. Use bilateral overlap:
```python
# Get file2's fingerprint count for bilateral comparison
other_fps = db.get_file_fingerprint_count(other_pid, other_path)
if other_fps > 0:
    sim_val = count / min(total_fps, other_fps)
```
This requires adding `get_file_fingerprint_count()` to `db.py`.

### 4.8 Make Thresholds Configurable
Lines 351, 361, 369, 372, 380, 386 all use hardcoded magic numbers. Read them from
the settings table instead:
```python
settings = db.get_all_settings()
code_threshold = settings.get("code_similarity_threshold", 0.25)
flag_threshold = settings.get("flag_threshold", 0.65)
```

### 4.9 Fix History File Race Condition
Add a threading lock around `_load_history` / `_save_history`:
```python
_history_lock = threading.Lock()

def _save_history(history):
    with _history_lock:
        HISTORY_FILE.write_text(json.dumps(history, default=str, indent=2), encoding="utf-8")
```

### 4.10 Fix N-Transaction SQLite Commit Storm in `_run_intake`
Lines 269–276: `db.store_fingerprints()` is called per-file, each opening and committing
separately. Batch all fingerprints into a single transaction:
```python
db.store_fingerprints_batch(project_name, all_fingerprints_dict)
```
Add `store_fingerprints_batch()` to `db.py` that does one `executemany` + one `commit`.

## Test Manually
1. Run a scan. Check Dashboard → Recent Scans shows the 10 MOST RECENT (not oldest).
2. Run a Deep Scan on two files. Verify it doesn't freeze the server.
3. Check Settings page thresholds are actually used in scan results.

---

# MODULE 5: FAISS Vector Search Integration

## Files to Read First
- `backend.py` lines 116–141 (_get_deep_scan_model), 199–294 (_run_intake), 1130–1220 (deep_scan)
- `requirements.txt`

## What to Do

### 5.1 Install faiss-cpu
Add to `requirements.txt`: `faiss-cpu>=1.7.4`

### 5.2 Create `plagiarism_engine/faiss_index.py`
A FAISS index manager that:
- Maintains two indices: one for code (UniXcoder embeddings), one for text (BGE-M3)
- Persists to disk at `data/faiss_index/`
- Maps `integer_id → {project_id, file_path}` via a JSON sidecar file
- Supports `add_embeddings()`, `search()`, `save()`, `load()`

### 5.3 Add FAISS Phase to `_run_intake`
After Winnowing (line 267), add Phase 4:
```python
log("[PHASE 4/4] 🧠 Computing semantic embeddings for FAISS...")
# Encode code files with UniXcoder, text files with BGE-M3
# Add normalized embeddings to the FAISS index
faiss_mgr.add_embeddings(embeddings, metadata, domain="code")
faiss_mgr.save()
```

### 5.4 Add Bulk Deep Scan Endpoint
```python
@app.post("/api/plagiarism/deep-scan-bulk")
async def deep_scan_bulk(req: BulkDeepScanRequest):
    """Find top-k most similar files across the entire database for a project."""
    # Encode project files → search FAISS index → return top matches
```

## DO NOT
- Do NOT delete Winnowing, ChromaDB, or `_cosine_similarity()`.
- FAISS is additive — it supplements existing systems.

## Test Manually
1. Upload a project. Verify FAISS index files appear in `data/faiss_index/`.
2. Upload a second similar project. Run bulk deep scan.
3. Verify results show semantically similar files across both projects.

---

# MODULE 6: Project-to-Project Comparison

## What to Do

### 6.1 Add Backend Endpoint
Add `POST /api/plagiarism/compare-projects` to `backend.py` that accepts two project
names and returns a file-pair similarity matrix using Winnowing hash overlap.
(See `phase_2_handoff_plan.md` Module 5 for the complete implementation.)

### 6.2 Add Frontend API Method
Add `compareProjects()` to `plagiarismApi` in `api.ts`.

### 6.3 Add Comparison UI to PlagiarismAnalysis.tsx
- Two project dropdown selectors
- "Compare" button
- Results table with file pairs, similarity %, and status badges
- Option to deep-scan individual file pairs from the results

### 6.4 Fix Deep Scan project_id Mismatch
In `PlagiarismAnalysis.tsx` line 59: Change `project_id: scanResult.project_name` to
use the actual project ID from the dropdown selection.

## Test Manually
1. Upload two projects.
2. Go to Plagiarism Scanner page.
3. Select Project A and Project B from two dropdowns.
4. Click "Compare". Verify file-pair results appear.

---

# MODULE 7: App Architecture & Error Boundaries

## What to Do

### 7.1 Add ErrorBoundary to App.tsx
Wrap `<Suspense>` with an `<ErrorBoundary>` that shows a retry button on chunk load
failures instead of a white screen crash.

### 7.2 Add Route Guards
Unauthenticated users can currently access `/projects`, `/teams`, `/users`, `/settings`.
Add a `ProtectedRoute` wrapper that checks `localStorage.getItem("auth_token")`.

### 7.3 Fix Accessibility
- Dropzone: Add `role="button"`, `tabIndex={0}`, `onKeyDown` for Enter/Space.
- Git tab inputs: Associate `<label>` with `<input>` via `htmlFor`/`id`.

## Test Manually
1. Open the app. Click around rapidly between pages.
2. Verify no white screen crashes.
3. Open DevTools → Console. Verify no uncaught errors.

---

# EXECUTION ORDER

```
Module 1 → Test → Module 2 → Test → Module 3 → Test → Module 4 → Test
    → Module 5 → Test → Module 6 → Test → Module 7 → Test
```

**After EACH module, stop and let the user test the UI manually at
http://localhost:3000 before proceeding to the next module.**
