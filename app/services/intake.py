"""Core scan pipeline: file intake/fingerprinting and similarity analysis."""

import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from plagiarism_engine import CodePlagiarismDetector, TextPlagiarismDetector
from app.state import _load_history, _save_history, get_db


# ---------------------------------------------------------------------------
# Utility: Run a full plagiarism scan on extracted files
# ---------------------------------------------------------------------------
def _run_intake(
    project_name: str,
    project_files: List[Dict[str, Any]],
    log_callback=None,
    git_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute code + text intake (extraction, Winnowing, and DB indexing)."""
    db = get_db()
    # PERF: the FAISS vector store is no longer touched during intake.
    # Deep semantic indexing (CodeBERT / BGE-M3 embeddings) is deferred to
    # Deep Scan mode, so the singleton is not even instantiated here.
    # Re-enable together with the `index_project_files()` block below.
    # vstore = get_vstore()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    from plagiarism_engine.winnowing import WinnowingEngine
    winnow = WinnowingEngine()

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log(f"[PHASE 1/3] 📂 Extracted {len(project_files)} files from '{project_name}'")

    # Central file-scope policy: every upload path (direct, streaming, ZIP, Git) passes through
    # here, so config / template / log / data files are never stored, fingerprinted or embedded.
    from plagiarism_engine.file_policy import filter_scannable
    project_files, excluded_files = filter_scannable(project_files)
    if excluded_files:
        reasons: Dict[str, int] = {}
        for item in excluded_files:
            reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        summary = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items()))
        log(f"   → Excluded {len(excluded_files)} non-scannable file(s) by policy ({summary})")
    if not project_files:
        raise ValueError(
            f"No scannable files in '{project_name}': all {len(excluded_files)} file(s) are config, template, "
            f"log/data, binary or unsupported types."
        )

    code_files = [f for f in project_files if f.get("file_type") == "code"]
    text_files = [f for f in project_files if f.get("file_type") == "text"]

    log(f"   → {len(code_files)} code files, {len(text_files)} text files")

    total_loc = 0
    languages: set = set()
    for f in project_files:
        content = f.get("content", "")
        total_loc += len([l for l in content.splitlines() if l.strip()])
        ext = f.get("extension", "")
        if ext:
            languages.add(ext.lstrip("."))

    log("[PHASE 2/3] 💾 Indexing project files into database (with Zlib compression)...")
    db.save_project(project_id=project_name, project_name=project_name, files=project_files)
    if metadata and hasattr(db, "update_project"):
        try:
            db.update_project(
                project_name,
                title=metadata.get("title"),
                abstract=metadata.get("abstract"),
                department=metadata.get("department"),
                year=metadata.get("year"),
                university=metadata.get("university"),
            )
        except Exception as e:
            log(f"   ℹ️ Metadata update note: {e}")

    # ------------------------------------------------------------------
    # PERF: Deep Semantic Indexing DECOUPLED from the upload stream.
    #
    # `VectorStore.index_project_files()` encoded every file with CodeBERT
    # (code) / BGE-M3 (text) and pushed the vectors into FAISS
    # (`add_with_ids` + `faiss.write_index`). That dominated upload latency
    # (minutes on large projects) while providing no value to the immediate
    # Winnowing result, so it is now DEFERRED to Deep Scan mode.
    #
    # The vector store itself is untouched and stays available for the
    # deferred Deep Scan indexer — to restore eager indexing, uncomment the
    # `vstore = get_vstore()` line at the top of this function plus the
    # block below.
    # ------------------------------------------------------------------
    log("[PHASE 2/3] Skipping Deep Semantic Indexing (Deferred to Deep Scan mode)...")
    # try:
    #     vstore.index_project_files(
    #         project_files=project_files,
    #         project_id=project_name,
    #         log_callback=log,
    #     )
    # except Exception as e:
    #     log(f"   ⚠️ Vector indexing warning: {e}")

    log("[PHASE 3/3] 🔮 Computing Winnowing fingerprints...")
    t0 = time.time()
    total_fingerprints = 0
    
    file_fingerprints = {}
    for idx, f in enumerate(project_files):
        content = f.get("content", "")
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        
        if not content.strip():
            continue
            
        if ftype == "code":
            fps = winnow.compute_code_fingerprints(content, rel_path)
        elif ftype == "text":
            fps = winnow.compute_text_fingerprints(content)
        else:
            continue
            
        file_fingerprints[rel_path] = fps
        total_fingerprints += len(fps)
        if idx > 0 and idx % 100 == 0:
            log(f"   → Computed fingerprints for {idx}/{len(project_files)} files...")
            
    t1 = time.time()
    log(f"   ✅ {total_fingerprints} fingerprints computed in {round(t1-t0, 1)}s")

    log("💾 Storing new fingerprints to database index (batch mode)...")
    batch = []
    for f in project_files:
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if fps:
            batch.append((rel_path, ftype, fps))
    db.store_fingerprints_batch(project_name, batch)
    try:
        from app.state import get_vstore
        from app.services.embeddings import _index_project_embeddings
        log("🤖 Indexing semantic vector embeddings into pgvector...")
        vstore = get_vstore()
        _index_project_embeddings(vstore, db, project_name)
        log("✅ Semantic embeddings indexed successfully.")
    except Exception as e:
        log(f"   ℹ️ Semantic embedding deferred: {e}")
    log(f"✅ Intake complete for project: {project_name}")

    result = {
        "status": "completed",
        "project_name": project_name,
        "code_files_count": len(code_files),
        "text_files_count": len(text_files),
        "total_files": len(project_files),
        "total_loc": total_loc,
        "languages_detected": sorted(languages),
        "timestamp": timestamp,
        "excluded_files": excluded_files,
        "excluded_files_count": len(excluded_files),
    }

    if git_metadata:
        result["git_metadata"] = git_metadata

    return result


def _run_analysis(
    project_name: str,
    log_callback=None,
) -> Dict[str, Any]:
    """Run plagiarism scan against existing corpus for a saved project."""
    db = get_db()
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log(f"[PHASE 1/4] 📂 Loading project '{project_name}' from database...")
    project_files = db.get_project_files(project_name)
    if not project_files:
        raise ValueError(f"Project '{project_name}' not found in database.")

    # Legacy guard: projects stored before the file-scope policy existed can still contain config,
    # template or log/data files. They are never scanned or scored (source or candidate side).
    from plagiarism_engine.file_policy import is_scannable

    def _scannable(path: str) -> bool:
        return is_scannable(path)[0]

    skipped_legacy = [f.get("relative_path", "") for f in project_files if not _scannable(f.get("relative_path", ""))]
    if skipped_legacy:
        log(f"   → Skipping {len(skipped_legacy)} stored file(s) excluded by the file-scope policy (config/template/log/data)")
        project_files = [f for f in project_files if _scannable(f.get("relative_path", ""))]
    if not project_files:
        raise ValueError(f"Project '{project_name}' has no scannable files (all are config/template/log/data).")

    code_files = [f for f in project_files if f.get("file_type") == "code"]
    text_files = [f for f in project_files if f.get("file_type") == "text"]
    
    total_loc = 0
    languages: set = set()
    for f in project_files:
        content = f.get("content", "")
        total_loc += len([l for l in content.splitlines() if l.strip()])
        ext = Path(f.get("relative_path", "")).suffix.lower()
        if ext:
            languages.add(ext.lstrip("."))

    log(f"[PHASE 2/4] 🔍 Querying fingerprint index for candidates ({len(code_files)} code, {len(text_files)} text files)...")
    
    # Fetch fingerprints for this project
    file_fingerprints = db.get_project_fingerprints(project_name)
    
    all_comparisons: List[Dict[str, Any]] = []
    max_code_sim = 0.0
    max_text_sim = 0.0

    total_candidates = 0

    # MOSS-style common-code suppression: fingerprints appearing in >= max(5, 5% of projects)
    # are shared boilerplate/framework templates and ignored during candidate discovery.
    from plagiarism_engine.config import (
        COMMON_FP_MIN_PROJECTS,
        COMMON_FP_FRACTION,
        SEMANTIC_ADMISSION_RAW,
        CODE_SEMANTIC_GATE,
    )
    all_proj_count = len(db.get_all_projects(limit=5000)) or 1
    max_fp_projects = max(COMMON_FP_MIN_PROJECTS, int(COMMON_FP_FRACTION * all_proj_count))
    min_code_fps = CODE_SEMANTIC_GATE.get("min_shared_fps", 3)

    # 1. Performance optimization: single SQL candidate query with suppression
    if hasattr(db, "query_project_candidates"):
        raw_candidates = db.query_project_candidates(
            project_id=project_name,
            max_common_projects=max_fp_projects,
            min_shared=1,
        )
        target_pids = set(c["target_project"] for c in raw_candidates)
        target_counts = db.get_file_fingerprint_counts_for_projects(target_pids) if hasattr(db, "get_file_fingerprint_counts_for_projects") else {}
        source_counts = {path: len(set(h for h, _ in fps)) for path, fps in file_fingerprints.items()}

        for c in raw_candidates:
            rel_path = c["source_file"]
            other_pid = c["target_project"]
            other_path = c["target_file"]
            count = c["shared"]
            ftype = c["file_type"]

            if not _scannable(other_path):
                continue

            total_fps = source_counts.get(rel_path, 0)
            target_fps = target_counts.get((other_pid, other_path))
            if target_fps is None:
                target_fps = db.get_file_fingerprint_count(other_pid, other_path)
            if not target_fps or not total_fps:
                continue

            # Symmetric candidate admission:
            # 1. Has at least min_code_fps (>= 3) shared fingerprints
            # 2. OR 100% exact match for a small file on either side (< 3 fps)
            is_small_exact = (total_fps < min_code_fps and count == total_fps) or (target_fps < min_code_fps and count == target_fps)
            if count < min_code_fps and not is_small_exact:
                continue

            total_candidates += 1
            sim_val = min(count / min(total_fps, target_fps), 1.0)
            if ftype == "code":
                if is_small_exact or (sim_val >= 0.15 and count >= 5) or sim_val >= 0.25:
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "raw_sim": sim_val,
                        "type": "Code",
                        "status": "SAFE",
                    })
            elif ftype == "text":
                if is_small_exact or (sim_val >= 0.15 and count >= 5) or sim_val >= 0.20:
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "raw_sim": sim_val,
                        "type": "Text",
                        "status": "SAFE",
                    })
    else:
        # Fallback per-file query path
        common_fps = set()
        if hasattr(db, "get_common_fingerprints"):
            try:
                all_source_hashes = set(h for fps in file_fingerprints.values() for h, _ in fps)
                common_fps = db.get_common_fingerprints(max_fp_projects, candidate_hashes=all_source_hashes)
            except Exception:
                pass

        for f in project_files:
            rel_path = f.get("relative_path", "")
            ftype = f.get("file_type", "")
            fps = file_fingerprints.get(rel_path, [])
            if not fps:
                continue
            fp_hashes = [h for h, p in fps if h not in common_fps] if common_fps else [h for h, p in fps]
            if not fp_hashes:
                continue
            total_fps = len(fp_hashes)
            candidates = db.query_candidates(fp_hashes, ftype, project_name)
            for key, count in candidates.items():
                other_pid, other_path = key.split("::", 1)
                if not _scannable(other_path):
                    continue
                target_fps = db.get_file_fingerprint_count(other_pid, other_path)
                if not target_fps:
                    continue
                is_small_exact = (total_fps < min_code_fps and count == total_fps) or (target_fps < min_code_fps and count == target_fps)
                if count < min_code_fps and not is_small_exact:
                    continue
                total_candidates += 1
                sim_val = min(count / min(total_fps, target_fps), 1.0)
                if ftype == "code":
                    if is_small_exact or (sim_val >= 0.15 and count >= 5) or sim_val >= 0.25:
                        all_comparisons.append({
                            "project": other_pid,
                            "file1": rel_path,
                            "file2": other_path,
                            "similarity": f"{round(sim_val * 100, 2)}%",
                            "raw_sim": sim_val,
                            "type": "Code",
                            "status": "SAFE",
                        })
                elif ftype == "text":
                    if is_small_exact or (sim_val >= 0.15 and count >= 5) or sim_val >= 0.20:
                        all_comparisons.append({
                            "project": other_pid,
                            "file1": rel_path,
                            "file2": other_path,
                            "similarity": f"{round(sim_val * 100, 2)}%",
                            "raw_sim": sim_val,
                            "type": "Text",
                            "status": "SAFE",
                        })

    # Top-K candidate pruning per source file to eliminate Cartesian product explosion
    if all_comparisons:
        by_source: Dict[str, List[Dict[str, Any]]] = {}
        for c_item in all_comparisons:
            by_source.setdefault(c_item["file1"], []).append(c_item)
        pruned: List[Dict[str, Any]] = []
        for src_path, c_list in by_source.items():
            c_list.sort(key=lambda x: x.get("raw_sim", 0.0), reverse=True)
            pruned.extend(c_list[:10])  # keep top 10 matches per source file
        pruned.sort(key=lambda x: x.get("raw_sim", 0.0), reverse=True)
        all_comparisons = pruned[:300]  # Cap candidate comparisons to top 300

    log(f"   ✅ Scan complete: {len(all_comparisons)} matches from {total_candidates} candidates.")

    # Phase 3: Hybrid Fusion Scoring (Winnowing + Semantic)
    log("[PHASE 3/4] 🧬 Running Hybrid Fusion Algorithm (Lexical + Semantic)...")
    from plagiarism_engine.fusion_scorer import compute_fusion_score
    from plagiarism_engine.winnowing import WinnowingEngine
    from app.state import get_vstore
    
    winnow_engine = WinnowingEngine()
    vstore = get_vstore()
    
    # Ensure the scanned project and every lexically matched project have current embeddings
    # (both are required to fuse those pairs). The scanned project is indexed first, and each
    # project is isolated so a single failing corpus project cannot disable semantic search.
    #
    # Semantic-only discovery (pairs Winnowing missed) searches the projects that ALREADY have
    # vectors. Quick Scan deliberately does not embed the rest of the corpus synchronously: on real
    # data a 3-file project with no lexical candidates otherwise spent 25+ minutes embedding ~870
    # files of unrelated projects. Deep Scan (deep-scan-bulk) still indexes the wider corpus.
    from app.services.embeddings import _index_project_embeddings
    candidate_projects = sorted({cmp["project"] for cmp in all_comparisons} - {project_name})
    projects_to_index = [project_name] + candidate_projects

    for pid in projects_to_index:
        try:
            if vstore.needs_reindex(pid):
                log(f"   🤖 Indexing missing/stale vectors for project '{pid}'...")
                _index_project_embeddings(vstore, db, pid)
        except Exception as e:
            log(f"   ⚠️ Semantic indexing failed for project '{pid}': {e}")

    try:
        unindexed = [
            p.get("id") or p.get("name") for p in db.get_all_projects(limit=200)
            if (p.get("id") or p.get("name")) not in projects_to_index
            and vstore.count_project_vectors(p.get("id") or p.get("name")) == 0
        ]
        if unindexed:
            log(f"   ℹ️ {len(unindexed)} corpus project(s) have no semantic vectors yet and are only covered "
                f"lexically in Quick Scan; run Deep Scan or POST /projects/{{id}}/index-embeddings to include them.")
    except Exception:
        pass

    # Fetch top semantic matches from Postgres 2-step rescoring store
    semantic_lookup = {}
    try:
        semantic_matches = vstore.search_bulk(project_name)
        existing_pairs = {(c["file1"], c["project"], c["file2"]) for c in all_comparisons}
        for m in semantic_matches:
            src_file = m.get("source_file", "")
            tgt_proj = m.get("matched_project_id") or m.get("target_project", "")
            tgt_file = m.get("matched_file") or m.get("target_file", "")
            sim = float(m.get("similarity", 0.0))
            raw_sim = float(m.get("similarity_raw", sim))
            model_used = m.get("embedding_model")
            domain = m.get("domain", "")

            if src_file and tgt_proj and tgt_file:
                if not (_scannable(src_file) and _scannable(tgt_file)):
                    continue
                key = (src_file, tgt_proj, tgt_file)
                semantic_lookup[key] = sim

                # Text semantic-only admission: raw >= SEMANTIC_ADMISSION_RAW[model]
                # Code is NEVER admitted semantic-only (requires >= 3 shared fingerprints).
                if key not in existing_pairs:
                    if domain == "text":
                        raw_threshold = SEMANTIC_ADMISSION_RAW.get(model_used, 0.885)
                        if raw_sim >= raw_threshold:
                            existing_pairs.add(key)
                            all_comparisons.append({
                                "project": tgt_proj,
                                "file1": src_file,
                                "file2": tgt_file,
                                "similarity": f"{round(sim * 100, 2)}%",
                                "type": "Text",
                                "status": "SAFE",
                            })
    except Exception as e:
        log(f"   ⚠️ Semantic search failed: {e}")

    # Pre-cache source contents for speed
    source_contents = {f.get("relative_path", ""): f.get("content", "") for f in project_files}

    # Pre-cache target files in batches per target project
    needed_by_project: Dict[str, List[str]] = {}
    for cmp in all_comparisons:
        needed_by_project.setdefault(cmp["project"], []).append(cmp["file2"])
    target_contents_cache: Dict[Tuple[str, str], str] = {}
    for opid, paths in needed_by_project.items():
        try:
            t_files = db.get_files_by_paths(project_name, list(set(paths)), target_project_id=opid)
            for tf in t_files:
                target_contents_cache[(opid, tf.get("relative_path"))] = tf.get("content", "") or ""
        except Exception:
            pass

    # Evaluate the top matches (or all of them) with the Fusion Engine
    max_fusion_score = 0.0
    final_verdict = "SAFE"
    report_rows = []
    total_cmps = len(all_comparisons)
    log(f"   🧬 Fusing {total_cmps} comparison pairs...")

    for idx, cmp in enumerate(all_comparisons):
        if idx > 0 and (idx % 25 == 0 or idx == total_cmps - 1):
            pct = round((idx / total_cmps) * 100)
            log(f"   ⚡ Fused {idx}/{total_cmps} comparisons ({pct}%)...")
        try:
            other_pid = cmp["project"]
            rel_path = cmp["file1"]
            other_path = cmp["file2"]
            source_content = source_contents.get(rel_path, "")
            target_content = target_contents_cache.get((other_pid, other_path))

            if target_content is None:
                # Fallback if not cached
                target_files = db.get_files_by_paths(project_name, [other_path], target_project_id=other_pid)
                target_content = target_files[0].get("content", "") if target_files else ""

            if source_content and target_content:
                # Get the pre-calculated Semantic Score from pgvector (fast O(1) lookup)
                sem_key = (rel_path, other_pid, other_path)
                precalc_semantic_score = semantic_lookup.get(sem_key, 0.0)

                # Execute Hybrid Fusion Math
                fusion_result = compute_fusion_score(
                    file_a_content=source_content,
                    file_b_content=target_content,
                    semantic_score=precalc_semantic_score,
                    file_type="code" if cmp.get("type") == "Code" else "text",
                    winnowing_engine=winnow_engine,
                    filename=rel_path,
                    filename_b=other_path,
                )

                # Update frontend comparison object
                cmp["similarity"] = f"{fusion_result['fusion_score']}%"  # Show fusion score as main
                cmp["winnowing_score"] = fusion_result["winnowing_score"]
                cmp["semantic_score"] = fusion_result["semantic_score"]
                cmp["fusion_score"] = fusion_result["fusion_score"]
                cmp["containment_score"] = fusion_result["containment_score"]
                cmp["embedded_copy"] = fusion_result["embedded_copy"]
                cmp["alpha"] = fusion_result["alpha"]
                cmp["status"] = fusion_result["verdict"]

                # Track global max score
                max_fusion_score = max(max_fusion_score, fusion_result["fusion_score"])
                if cmp.get("type") == "Code":
                    max_code_sim = max(max_code_sim, fusion_result["fusion_score"])
                else:
                    max_text_sim = max(max_text_sim, fusion_result["fusion_score"])

                # Collect for batched scan_reports insert
                report_id = f"report_{uuid.uuid4().hex[:8]}"
                report_rows.append((
                    report_id,
                    f"{project_name}::{rel_path}",
                    f"{other_pid}::{other_path}",
                    fusion_result["fusion_score"],
                    fusion_result["winnowing_score"],
                    fusion_result["semantic_score"],
                    fusion_result["fusion_score"],
                    fusion_result["alpha"],
                    fusion_result["verdict"],
                    cmp.get("type", "unknown"),
                    "Hybrid Fusion",
                ))
            else:
                cmp["fusion_score"] = 0.0
                cmp["winnowing_score"] = 0.0
                cmp["semantic_score"] = 0.0
                cmp["containment_score"] = 0.0
                cmp["embedded_copy"] = False
                cmp["alpha"] = 1.0
                cmp["status"] = "SAFE"
                cmp["similarity"] = "0.0%"
        except Exception as e:
            cmp["fusion_score"] = 0
            cmp["status"] = "ERROR"
            print(f"Fusion error on {cmp.get('file1')}: {e}")

    # Phase 4: Compile Final Integrity Report & Save
    log("[PHASE 4/4] 📊 Compiling final integrity report and storing results in database...")

    # Store all scan_reports in database via a single transaction / executemany
    if report_rows and hasattr(db, 'mode'):
        conn = db._get_connection()
        try:
            cur = conn.cursor()
            if db.mode == "postgresql":
                cur.executemany("""
                    INSERT INTO scan_reports (id, query_id, target_id, similarity_score, winnowing_score, semantic_score, fusion_score, alpha, verdict, match_type, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                """, report_rows)
            else:
                cur.executemany("""
                    INSERT OR REPLACE INTO scan_reports (id, query_id, target_id, similarity_score, winnowing_score, semantic_score, fusion_score, alpha, verdict, match_type, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, report_rows)
            conn.commit()
        except Exception as e:
            conn.rollback()
            log(f"   ⚠️ Failed to save scan_reports in batch: {e}")
        finally:
            conn.close()

    overall = max_fusion_score
    from plagiarism_engine.fusion_scorer import verdict_for
    verdict = verdict_for(overall / 100.0)

    log(f"✅ Full run complete. Overall similarity: {overall}% — Verdict: {verdict}")

    try:
        threshold_val = int(db.get_setting("similarity_threshold", 65))
    except Exception:
        threshold_val = 65

    result = {
        "status": "completed",
        "id": scan_id,
        "project_name": project_name,
        "overall_similarity": overall,
        "code_similarity": round(max_code_sim, 2),
        "text_similarity": round(max_text_sim, 2),
        "verdict": verdict,
        "threshold": threshold_val,
        "comparisons": sorted(
            [c for c in all_comparisons if float(str(c.get("fusion_score") or c.get("similarity") or "0").replace("%", "")) > 0] or all_comparisons[:20],
            key=lambda x: float(str(x.get("fusion_score") or x.get("similarity") or "0").replace("%", "")),
            reverse=True
        )[:150],
        "code_files_count": len(code_files),
        "text_files_count": len(text_files),
        "total_files": len(project_files),
        "total_loc": total_loc,
        "languages_detected": sorted(languages),
        "timestamp": timestamp,
    }

    # Persist to history
    history = _load_history()
    history.insert(0, result)
    _save_history(history)

    return result
