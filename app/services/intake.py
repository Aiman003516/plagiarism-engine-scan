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

    # Phase 3: ML-enhanced verification on top Winnowing matches
    log("[PHASE 3/3] 🤖 Running ML verification on top matches...")
    code_detector = CodePlagiarismDetector()
    text_detector = TextPlagiarismDetector()

    for cmp in all_comparisons[:20]:  # Only verify top 20 to save time
        try:
            other_pid = cmp["project"]
            source_content = ""
            target_content = ""

            # Get source file content
            for f in project_files:
                if f.get("relative_path", "") == cmp.get("file1", ""):
                    source_content = f.get("content", "")
                    break

            # Get target file content from DB.
            # NOTE: get_files_by_paths() excludes the project_id passed to it, so we pass the
            # *source* project and then select the row belonging to the matched (other) project.
            target_files = db.get_files_by_paths(project_name, [cmp.get("file2", "")])
            matched = [
                t for t in target_files
                if t.get("project_id") == other_pid and t.get("relative_path") == cmp.get("file2", "")
            ]
            if matched:
                target_content = matched[0].get("content", "")
            elif target_files:
                target_content = target_files[0].get("content", "")

            if source_content and target_content:
                if cmp.get("type") == "Code":
                    # compare_code() reports its hybrid composite score under the "similarity" key.
                    ml_result = code_detector.compare_code(source_content, target_content)
                    cmp["ml_similarity"] = f"{round(ml_result.get('similarity', 0) * 100, 2)}%"
                else:
                    ml_result = text_detector.compare_pair(source_content, target_content)
                    cmp["ml_similarity"] = f"{round(ml_result.get('similarity', 0) * 100, 2)}%"
        except Exception as e:
            cmp["ml_similarity"] = "N/A"

    overall = round(max(max_code_sim, max_text_sim) * 100, 2)
    verdict = "FLAGGED" if overall >= 65 else "SAFE"

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
