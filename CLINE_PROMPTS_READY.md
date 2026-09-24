# Ready-to-Paste Prompts for Cline (DeepSeek V4 / Claude Opus 4.6)
# Copy-paste ONE prompt at a time. Test after each. Then paste the next.

---

## 🟢 PROMPT 1 — Before Starting (Paste This FIRST, Before Any Module)

```
You are working on a plagiarism detection system at:
C:\Users\Ayman\Downloads\plagiarism_engine_scan\

Read the file CLINE_PROMPT.md in the project root. It contains the full project
layout, all known bugs, and 7 fix modules. DO NOT execute any module yet.

After reading it, tell me:
1. How many modules are there?
2. What is Module 1 about?
3. What files will Module 1 modify?

Do NOT write any code yet. Just confirm you understand the codebase.
```

> **WHY:** This forces the model to read the entire CLINE_PROMPT.md first and prove
> it understands the project before touching anything. If it can't answer these 3
> questions correctly, it hasn't read the file properly — tell it to read it again.

---

## 🟢 PROMPT 2 — Execute Module 1 (Zustand Global State)

```
Good. Now execute Module 1 from CLINE_PROMPT.md.

IMPORTANT: There are TWO groups of state that must survive page navigation:

Group A (pre-scan): uploadedFiles, projectName, isProcessingFiles, isTraversing,
totalFilesToProcess, processedFilesCount, processingPhase, bloatFilteredCount,
inspectedTotalNodes — these are the staged files and progress bars you see BEFORE
clicking the Index button.

Group B (scan execution): isScanning, scanLogs, scanResult, scanError — these are
the terminal stream and results you see AFTER clicking the Index button.

BOTH groups must be in the Zustand store. The user must be able to:
1. Upload files and see "31/31 Scanning directory structure" progress
2. Navigate to Dashboard
3. Come back to Intake — and see those 31 files still staged with the progress intact

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- Read Plagiarism.tsx lines 140–180 to see ALL useState hooks.
- Make surgical edits only. Do NOT rewrite entire files.
- Do NOT delete readZipScanStream (lines 54–132 of Plagiarism.tsx). It works.
- KEEP as local useState: activeTab, isDragging, showExplorer, stagedSearch,
  stagedCategory, terminalAutoScroll, lastLogTimestamp, timeSinceLastLog,
  isHistoryOpen, historyList, isLoadingHistory, historySearch, and all git-related state.
- After you're done, show me a summary of every file you created or modified and what changed.

Start now.
```

---

## 🟢 PROMPT 3 — After Testing Module 1

If Module 1 works:
```
Module 1 is tested and working. Now execute Module 2 from CLINE_PROMPT.md.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- Make surgical edits only. Do NOT rewrite entire files.
- Fix all 7 bugs listed (2A through 2G).
- When fixing Bug 2A and 2B, use the existing plagiarismApi.uploadZipStream() from
  api.ts instead of the raw fetch(). Do NOT write a new SSE parser.
- After you're done, show me a summary of every file you modified and what changed.

Start now.
```

If Module 1 has issues:
```
Module 1 is NOT working. Here is the problem:
[DESCRIBE WHAT YOU SEE — paste the error from the browser console or describe the UI behavior]

Fix this before moving to the next module. Do NOT proceed to Module 2.
```

---

## 🟢 PROMPT 4 — After Testing Module 2

If Module 2 works:
```
Module 2 is tested and working. Now execute Module 3 from CLINE_PROMPT.md.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- All THREE SSE endpoints must be refactored (upload-scan-stream, upload-zip-stream, git-scan-stream).
- Use asyncio.Queue for real-time log streaming. Do NOT keep the logs=[] buffering pattern.
- Wrap _clone_git_repo in run_in_executor so it doesn't block the event loop.
- Add try/finally cleanup for temp directories in _clone_git_repo.
- After you're done, show me a summary of every file you modified and what changed.

Start now.
```

---

## 🟢 PROMPT 5 — After Testing Module 3

If Module 3 works:
```
Module 3 is tested and working. Now execute Module 4 from CLINE_PROMPT.md.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- This module has 10 sub-fixes (4.1 through 4.10). Execute ALL of them.
- For fix 4.1 (history wipe): create a backup file before returning empty list.
- For fix 4.7 (asymmetric similarity): you must add get_file_fingerprint_count() to db.py.
- For fix 4.10 (commit storm): you must add store_fingerprints_batch() to db.py.
- After you're done, show me a summary of every file you modified and what changed.

Start now.
```

---

## 🟢 PROMPT 6 — After Testing Module 4

If Module 4 works:
```
Module 4 is tested and working. Now execute Module 5 from CLINE_PROMPT.md.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- FAISS is ADDITIVE. Do NOT delete Winnowing, ChromaDB, or _cosine_similarity().
- Create plagiarism_engine/faiss_index.py as a new file.
- The FAISS index must persist to disk at data/faiss_index/.
- Add faiss-cpu>=1.7.4 to requirements.txt.
- After you're done, show me a summary of every file you created or modified and what changed.

Start now.
```

---

## 🟢 PROMPT 7 — After Testing Module 5

If Module 5 works:
```
Module 5 is tested and working. Now execute Module 6 from CLINE_PROMPT.md.

Also read phase_2_handoff_plan.md Module 5 section for the complete backend
implementation with the CompareProjectsRequest model and the compare-projects endpoint.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- This adds a NEW endpoint. Do NOT modify _run_analysis() or deep_scan().
- The frontend needs two project dropdowns, a compare button, and a results table.
- Fix the project_id mismatch in PlagiarismAnalysis.tsx line 59.
- After you're done, show me a summary of every file you created or modified and what changed.

Start now.
```

---

## 🟢 PROMPT 8 — After Testing Module 6

If Module 6 works:
```
Module 6 is tested and working. Now execute Module 7 from CLINE_PROMPT.md.

RULES:
- Read the "Files to Read First" section BEFORE writing any code.
- Add an ErrorBoundary component that catches chunk load failures and shows a retry button.
- Add a ProtectedRoute wrapper for authenticated pages.
- Fix accessibility: Dropzone role="button" + tabIndex, label htmlFor/id on git inputs.
- After you're done, show me a summary of every file you created or modified and what changed.

Start now.
```

---

## 🔴 EMERGENCY PROMPTS (Use If Things Go Wrong)

### If the model starts rewriting entire files:
```
STOP. You are rewriting the entire file. I said surgical edits only.
Revert what you just did and make only the specific changes listed in the module.
Do NOT replace the entire file content.
```

### If the model breaks something that was working:
```
STOP. You broke [describe what broke]. The [feature] was working before your changes.
Undo your last change to [filename] and try a different approach.
Show me what you changed so I can understand what went wrong.
```

### If the model skips ahead to the next module:
```
STOP. I did not ask you to start Module [N+1]. I asked for Module [N] only.
Finish Module [N] first. Do NOT touch any files related to other modules.
```

### If you want to see what it changed:
```
Show me a diff of every file you modified. List the filename, the line numbers
you changed, what the old code was, and what the new code is.
```

---

## 💾 BACKUP COMMAND (Run Before Each Module in PowerShell)

```powershell
Compress-Archive -Path "C:\Users\Ayman\Downloads\plagiarism_engine_scan" -DestinationPath "C:\Users\Ayman\Downloads\backup_before_module_X.zip" -Force
```
Change `X` to the module number (1, 2, 3, etc.) before running.
