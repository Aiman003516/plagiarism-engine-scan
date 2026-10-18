# Plagiarism Engine — Status Report (what was fixed, what still needs fixing)

**Project:** `C:\Users\Ayman\Downloads\plagiarism_engine_scan`
**Date:** 2026-10-18 · **Git:** HEAD still `c7612ec` — nothing committed (all changes are uncommitted working-tree edits).
**Work stopped at the user's request.** All background tasks and Python processes were terminated.

> [!WARNING]
> **The full test suite was NOT re-run after the last batch of fixes.** The last complete run passed
> 14/15 tests (only `test_12` failed). Six later fixes (§2.3 – §2.8) are unverified by the suite. The
> first thing to do next is run `python -m unittest discover -s tests -p "test_*.py" -v`.

---

## 1. Timeline in one paragraph
Round 1 (Gemini 4 Argon) fixed the four defects that made the semantic layer non-functional (pool crash,
768 vs 1024 dimension mismatch, wrong dict keys, CWD-dependent storage). The round-1 review (Claude Opus 5.5)
found that the code embedding model (`codebert-base`) rated **unrelated code 95–98% similar**, so code
semantic scores were meaningless, and listed the leftover audit items. Round 2 (this round) fixed that with
measured model selection and calibration, then moved to testing on the user's real project folders. That testing found
five more real bugs, which were fixed. It ended before the final verification run.

---

## 2. What was fixed

### 2.1 Round-2 spec tasks (from `argon_handoff_round2.md`)

| Task | Status | Evidence / notes |
|---|---|---|
| **T1** Embedding-model provenance | ✅ Done, tested | `embedding_model` column (PG + SQLite). `LazyModelPool.get_model_with_name()` returns the *actually loaded* model, with no silent MiniLM substitution. Rows from different models are never compared. `needs_reindex()` replaces `count == 0`. `test_13` passed. |
| **T2** Code model chosen from evidence | ✅ Done | `scripts/calibrate_semantic_models.py` (10+10 code pairs in Py/Java/JS; 8+8 EN and 8+8 AR texts, ≥ 60 words). **`codebert-base` AUC 0.970, margin −0.001 → `unixcoder-base` AUC 1.000, margin +0.228.** Text stays on `bge-m3`. Results are in `calibration_results.md`. |
| **T3** Score calibration | ✅ Done, tested | `calibrate_semantic()` with per-model floors in `config.py` (unixcoder 0.30, bge-m3 0.72, codebert 0.98). Search returns `similarity` (calibrated) + `similarity_raw`. `test_09` passed. |
| **T4** Real discrimination test | ⚠️ Written, **last run failed** | `test_12` (renamed/restructured code, EN and AR paraphrase vs unrelated). It failed because semantic indexing silently crashed (see §2.3 and §2.4). Both causes were fixed afterwards and the test setup was adjusted (§2.8), but it **was not re-run**. |
| **T5** Unified deep-scan | ✅ Done (build passes) | Single-pair deep-scan uses the same model pool, calibration, and `verdict_for()` scale as the pipeline. Frontend badge updated (no `CONFIRMED_PLAGIARISM` left). |
| **T6** Containment signal | ✅ Done, tested | `containment_score` + `embedded_copy` per comparison; fusion formula unchanged (Jaccard). `test_14` passed (6-line function in a 247-line file → Jaccard 6.3%, containment 100%, flagged). |
| **T7** Mixed-language α | ✅ Done, tested | Mixed Arabic/English text → α = 0.25. Docs updated. `test_15` passed. |
| **T8** Secrets/config | ✅ Done | `JWT_SECRET`, `DATABASE_URL`, `STORAGE_BACKEND`, `APP_ENV` added to git-ignored `.env`. The app refuses to start in `APP_ENV=production` without a secret. The "JWT_SECRET not set" warning no longer appears. |
| **T9** Hard-coded credentials | ✅ Done | The admin connection is derived from `DATABASE_URL` via `parse_dsn`, and the DB is created with `sql.Identifier`. No `postgres:postgres` remains in `connection.py` (the dev default still exists in `helpers.py`, with a one-time warning when used). |
| **T10** Batched vector search | ⚠️ Code done, **benchmark not run** | One `LATERAL` query per scan replaces one query per file, and each embedding is fetched once. Real-corpus Deep Scan: **0.25–2.8 s per project** (522-file project ≈ 2.7 s). `scripts/bench_vector_search.py` (old-vs-new + top-5 agreement) was written but **never executed**. The pgvector branch is untested (pgvector is not installed). |
| **T11** FAISS leftovers | ✅ Done | `faiss-cpu` removed from requirements. `bench_faiss_before.py`, `faiss_mapping.json`, `chroma_db/`, `faiss_index/` moved to `archive/legacy_faiss/` (nothing deleted). `hybrid_service.py` has 0 importers. |
| **T12** Valid test PDF | ✅ Done | Real xref offsets; the "incorrect startxref pointer" warning is gone. |
| **T13** Frontend split | ⏭️ Skipped | Optional; not started. |

### 2.2 Bug fixed: CodeBERT made code similarity meaningless (from the review)
Raw `codebert-base` scored unrelated code at 0.95–0.98 cosine, so every code pair looked plagiarized at the
semantic level. It was replaced by `unixcoder-base`, chosen by AUC on the calibration set, and scores are now calibrated per model.

### 2.3 Bug fixed: UniXcoder crashed on long files (found by `test_12`)
`index 1026 is out of bounds`: the local checkpoint had no `max_seq_length`, so inputs over ~1024 tokens overflowed
the position table. `_cap_max_seq_length()` now clamps every model (RoBERTa-family: positions − 2, ceiling 512).

### 2.4 Bug fixed: one failing project disabled semantic search for the whole scan (found by `test_12`)
A single indexing exception (from the user's `AI engine_export_fixed` project) aborted the indexing loop **before
the scanned project itself was indexed**, so the scan silently returned zero semantic matches. The scanned project is now
indexed first and failures are isolated per project (Quick Scan and bulk Deep Scan).

### 2.5 Bug fixed: interrupted indexing was reported as "up to date" (found on real data)
A half-embedded project (e.g. the user's `Mizan_Monorepo`, 128/510 files) passed `needs_reindex()` because every
vector it *had* used the current model, so it would never have been completed. Files that are neither embedded nor marked
`skipped:empty` now trigger re-indexing.

### 2.6 Bug fixed: Winnowing dead zone, where identical files scored 0% (found on real data)
Files with **50–58 code tokens** (k ≤ tokens < k + w − 1) were too long for the small-file exact-match path but too
short for one Winnowing window, so they got **zero fingerprints**. On real data, byte-identical `auth.py` and `main.tsx`
copies scored Winnowing 0% (SAFE/LOW). They now keep the minimum hash, which is standard Winnowing.
`scripts/backfill_fingerprints.py` re-added the missing fingerprints for all 15 stored projects (additive only).

### 2.7 Bug fixed: Quick Scan could silently embed the whole corpus (found on real data)
When a scan found no lexical candidates, it synchronously embedded the 25 most recent projects. A 3-file project
spent 25+ minutes embedding ~870 unrelated files. Quick Scan now embeds only the scanned project and its lexical
candidates, logs which corpus projects lack vectors, and leaves full-corpus indexing to Deep Scan.

### 2.8 Test adjustment that follows from §2.7
`test_12` now indexes its corpus projects through the public `/projects/{id}/index-embeddings` endpoint before
scanning. **Its assertions are unchanged.**

---

## 3. Real-corpus evaluation (user's own folders) — partial

8 projects were ingested and embedded (1,353 files): `mizan_monorepo`, `3d-react-website`, `accounting`, `AI engine`,
`AI surveillance system`, `application of TinyML`, `C# accounting app(Mizan)`, `crystal-helix-erp`. The rest were cancelled
at the user's request. `Compressed` contains only zipped model weights; `manus-like agent/repos` (third-party clones) was excluded.

| Check | Result |
|---|---|
| Deep Scan speed | ✅ 0.25–2.8 s per project |
| True positives (Quick Scan, before the dead-zone fix) | ✅ `ai_engine` ↔ older `AI engine_export_fixed`: 251 file matches, 115 CRITICAL. `mizan_monorepo` ↔ older `Mizan_Monorepo`: 100% CRITICAL. `accounting` ↔ Mizan code: 100% CRITICAL |
| Quick Scan speed | 1.7–38.5 s per project (when no one-time embedding is needed) |
| **False positives** | ⚠️ Semantic-only matches between **unrelated** projects land at **LOW (~30%)** instead of SAFE: `index.css`↔`index.css`, `package.json`↔`pyproject.toml`, React component↔Vue page, Pydantic schema↔Pydantic schema |
| Final Quick Scan with all fixes | ❌ Not completed (stopped) |

Raw data: `real_corpus_eval/` (`size.json`, `ingest.json`, `embed.json`, `deep.json`, `quick_before_deadzone_fix.json`).

---

## 4. What still needs fixing

### Must do first
1. **Run the test suite.** Six fixes (§2.3–§2.8) are unverified; `test_12` has never passed.
2. **Run `scripts/bench_vector_search.py`** to confirm the batched search returns the same top-5 as the old search (≥ 95%) and measure the speed-up. Then replace the unmeasured "< 2 ms over millions of records" claim in `UNIFIED_POSTGRES_ARCHITECTURE.md` (line ~45) with real numbers. **Not done yet.**

### Real-data precision problem (most important open issue)
3. **Boilerplate false positives.** Any pair that enters through the semantic-only path (calibrated ≥ 0.70) gets fusion ≥ ~0.28, which is **LOW, never SAFE**. Same-framework boilerplate (CSS resets, `index.html`, manifests, schema classes) sits well above the synthetic "unrelated" floor. Options:
   - raise the semantic-only inclusion threshold;
   - require some lexical evidence before a semantic-only pair can exceed SAFE;
   - exclude manifest/boilerplate files (`package.json`, `pyproject.toml`, `index.html`, `*.css`, `styles.xml`);
   - re-measure calibration floors on **real** same-framework unrelated pairs instead of synthetic cross-domain pairs.
4. **Calibration data is synthetic.** Floors should be re-measured on real submissions (e.g. Ibb University Arabic PDFs).

### Engine design issues found on real data
5. **Ingest treats logs and data as "text"**: `android_build_log.txt` (1.4 MB), `train.csv` (5 MB). Add log/data extensions or size rules to the extractor.
6. `scan_project_directory`: the `MAX_TOTAL_SIZE` `break` only exits the inner loop (it keeps walking other directories).
7. **CPU embedding cost**: ~1.8 s per file (522-file project ≈ 16 min). Consider GPU, a smaller text model, or background indexing at upload.
8. **Small-file rule hides identical tiny files**: files below k whitespace tokens get α = 1.0, so semantic 100% is ignored and a near-identical tiny file can be SAFE. This is by design, but it should be reviewed.

### Leftover items not done
9. **T13**: frontend split of `PlagiarismAnalysis.tsx` (605 lines) and `UploadSection.tsx` (506 lines).
10. **pgvector branch** of the batched search is untested (pgvector is not installed).
11. `DEFAULT_PG_URL` in `db/helpers.py` still holds dev credentials (it warns once when used).
12. Whether `embedded_copy` should raise the verdict is an open research decision (currently informational only).

---

## 5. Database / workspace state left behind
- **8 evaluation projects** remain in the DB with the prefix `realeval_*` (fully embedded). Remove them with `python scripts/real_corpus_eval.py --phase cleanup`.
- **User project `Mizan_Monorepo`**: the last (stopped) Quick Scan had started rebuilding its embeddings, so they are partial again. The §2.5 fix makes the next scan detect this and re-index it automatically.
- Fingerprints were backfilled for all 15 projects (additive, nothing removed).
- Legacy FAISS files are in `archive/legacy_faiss/`.
- Test leftovers (`pytest_*`, `bench_*`) were cleaned up.

## 6. Files changed in Round 2
**Modified:** `plagiarism_engine/vectors/pgvector_store.py` (448 lines), `plagiarism_engine/vector_store.py` (299), `plagiarism_engine/fusion_scorer.py` (102), `plagiarism_engine/config.py` (57), `plagiarism_engine/winnowing.py` (145), `plagiarism_engine/db/schema.py` (313), `plagiarism_engine/db/connection.py` (128), `app/services/intake.py` (403), `app/routers/deep_scan.py` (213), `app/dependencies.py` (83), `frontend/src/pages/PlagiarismAnalysis.tsx` (605), `frontend/src/lib/api.ts` (806), `tests/test_engine_and_api.py` (815), `HYBRID_ARCHITECTURE.md` (393), `PHASE_6_FUSION_RESEARCH_LOG.md` (63), `requirements.txt` (26), `.env.example` (22), `.env` (git-ignored).
**Created:** `scripts/calibrate_semantic_models.py` (1171), `scripts/bench_vector_search.py` (207), `scripts/real_corpus_eval.py` (393), `scripts/backfill_fingerprints.py` (79), `calibration_results.md` (44), `real_corpus_eval/` (results).
**Moved:** FAISS leftovers → `archive/legacy_faiss/`.
**Verified:** frontend `npm run build` ✓ (37.7 s). **Not verified:** test suite after §2.3–§2.8, benchmark.
