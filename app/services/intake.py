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

    log(f"[PHASE 1/3] 📂 Loading project '{project_name}' from database...")
    project_files = db.get_project_files(project_name)
    if not project_files:
        raise ValueError(f"Project '{project_name}' not found in database.")
        
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

    log("[PHASE 2/3] 🔍 Querying fingerprint index for candidates...")
    
    # Fetch fingerprints for this project
    file_fingerprints = db.get_project_fingerprints(project_name)
    
    all_comparisons: List[Dict[str, Any]] = []
    max_code_sim = 0.0
    max_text_sim = 0.0

    total_candidates = 0

    for f in project_files:
        rel_path = f.get("relative_path", "")
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        
        if not fps:
            continue
            
        fp_hashes = [h for h, p in fps]
        total_fps = len(fp_hashes)
        
        candidates = db.query_candidates(fp_hashes, ftype, project_name)
        
        # Filter candidates: must share at least 5 fingerprints or 10%
        valid_candidates = {key: count for key, count in candidates.items() if count >= 5 or (count / total_fps) > 0.1}
        total_candidates += len(valid_candidates)
        
        for key, count in valid_candidates.items():
            other_pid, other_path = key.split("::", 1)
            
            target_fps = db.get_file_fingerprint_count(other_pid, other_path)
            if not target_fps:
                continue
                
            # Overlap coefficient: shared / min(source, target) allows detecting small files pasted inside large ones
            sim_val = min(count / min(total_fps, target_fps), 1.0)
            
            if ftype == "code":
                if sim_val >= 0.25:  # Lowered threshold to see results
                    max_code_sim = max(max_code_sim, sim_val)
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "type": "Code",
                        "status": "FLAGGED" if sim_val >= 0.65 else "Moderate"
                    })
            elif ftype == "text":
                if sim_val >= 0.20:
                    max_text_sim = max(max_text_sim, sim_val)
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "type": "Text",
                        "status": "FLAGGED" if sim_val >= 0.5 else "Moderate"
                    })

    log(f"   ✅ Scan complete: {len(all_comparisons)} matches from {total_candidates} candidates.")

    # Phase 3: Hybrid Fusion Scoring (Winnowing + Semantic)
    log("[PHASE 3/3] 🧬 Running Hybrid Fusion Algorithm (Lexical + Semantic)...")
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
            if src_file and tgt_proj and tgt_file:
                key = (src_file, tgt_proj, tgt_file)
                semantic_lookup[key] = sim
                # Include high-confidence semantic matches even if lexical Winnowing missed them (pure paraphrase)
                if sim >= 0.70 and key not in existing_pairs:
                    existing_pairs.add(key)
                    domain_label = "Code" if m.get("domain") == "code" else "Text"
                    all_comparisons.append({
                        "project": tgt_proj,
                        "file1": src_file,
                        "file2": tgt_file,
                        "similarity": f"{round(sim * 100, 2)}%",
                        "type": domain_label,
                        "status": "FLAGGED" if sim >= 0.76 else "Moderate",
                    })
    except Exception as e:
        log(f"   ⚠️ Semantic search failed: {e}")

    # Pre-cache source contents for speed
    source_contents = {f.get("relative_path", ""): f.get("content", "") for f in project_files}

    # Evaluate the top matches (or all of them) with the Fusion Engine
    max_fusion_score = 0.0
    final_verdict = "SAFE"
    
    for cmp in all_comparisons:
        try:
            other_pid = cmp["project"]
            rel_path = cmp["file1"]
            other_path = cmp["file2"]
            source_content = source_contents.get(rel_path, "")
            target_content = ""

            # Get target file content from DB filtered by exact target project_id
            target_files = db.get_files_by_paths(project_name, [other_path], target_project_id=other_pid)
            if target_files:
                target_content = target_files[0].get("content", "")

            if source_content and target_content:
                # Get the pre-calculated Semantic Score from pgvector (or compute pair similarity if not in top-k)
                sem_key = (rel_path, other_pid, other_path)
                precalc_semantic_score = semantic_lookup.get(sem_key)
                if precalc_semantic_score is None:
                    precalc_semantic_score = vstore.get_pair_similarity(project_name, rel_path, other_pid, other_path)

                # Execute Hybrid Fusion Math
                fusion_result = compute_fusion_score(
                    file_a_content=source_content,
                    file_b_content=target_content,
                    semantic_score=precalc_semantic_score,
                    file_type="code" if cmp.get("type") == "Code" else "text",
                    winnowing_engine=winnow_engine,
                    filename=rel_path,
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

                # Store in PostgreSQL scan_reports
                report_id = f"report_{uuid.uuid4().hex[:8]}"
                if hasattr(db, 'mode'):  # Standard projects_store usage
                    conn = db._get_connection()
                    try:
                        cur = conn.cursor()
                        if db.mode == "postgresql":
                            cur.execute("""
                                INSERT INTO scan_reports (id, query_id, target_id, similarity_score, winnowing_score, semantic_score, fusion_score, alpha, verdict, match_type, details)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (id) DO NOTHING;
                            """, (report_id, f"{project_name}::{rel_path}", f"{other_pid}::{other_path}", fusion_result["fusion_score"], fusion_result["winnowing_score"], fusion_result["semantic_score"], fusion_result["fusion_score"], fusion_result["alpha"], fusion_result["verdict"], cmp.get("type", "unknown"), "Hybrid Fusion"))
                        else:
                            cur.execute("""
                                INSERT OR REPLACE INTO scan_reports (id, query_id, target_id, similarity_score, winnowing_score, semantic_score, fusion_score, alpha, verdict, match_type, details)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """, (report_id, f"{project_name}::{rel_path}", f"{other_pid}::{other_path}", fusion_result["fusion_score"], fusion_result["winnowing_score"], fusion_result["semantic_score"], fusion_result["fusion_score"], fusion_result["alpha"], fusion_result["verdict"], cmp.get("type", "unknown"), "Hybrid Fusion"))
                        conn.commit()
                    finally:
                        conn.close()

        except Exception as e:
            cmp["fusion_score"] = 0
            cmp["status"] = "ERROR"
            print(f"Fusion error on {cmp['file1']}: {e}")

    overall = max_fusion_score
    from plagiarism_engine.fusion_scorer import verdict_for
    verdict = verdict_for(overall / 100.0)

    log(f"✅ Full run complete. Overall similarity: {overall}% — Verdict: {verdict}")

    result = {
        "status": "completed",
        "id": scan_id,
        "project_name": project_name,
        "overall_similarity": overall,
        "code_similarity": round(max_code_sim * 100, 2),
        "text_similarity": round(max_text_sim * 100, 2),
        "verdict": verdict,
        "threshold": 65,
        "comparisons": all_comparisons,
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
