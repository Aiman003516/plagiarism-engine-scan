"""Project-vs-project and file-vs-file comparison endpoints."""

import os
import asyncio
import difflib
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, Depends, File, UploadFile
import tempfile
from pathlib import Path
from plagiarism_engine.extractor import FileExtractor
from plagiarism_engine.file_policy import file_type_for
from plagiarism_engine.fusion_scorer import compute_fusion_score
from plagiarism_engine.winnowing import WinnowingEngine
from pydantic import BaseModel


from fastapi import APIRouter
from app.dependencies import require_role
from app.state import DATA_DIR, get_db
from plagiarism_engine.file_policy import is_scannable

router = APIRouter(tags=["compare"])


class ProjectComparisonRequest(BaseModel):
    project_a: str
    project_b: str


def _run_project_comparison(project_a: str, project_b: str) -> List[Dict[str, Any]]:
    """Compare project_a against ONLY project_b using the fingerprint index.

    For every file in project_a, queries the shared fingerprint index and
    keeps only candidates belonging to project_b. Similarity is the overlap
    coefficient: shared / min(file_a_fps, file_b_fps), which also catches
    small files pasted inside larger ones. Matches below 20% are dropped
    and results are sorted by highest similarity first.
    """
    db = get_db()
    project_files = db.get_project_files(project_a)
    file_fingerprints = db.get_project_fingerprints(project_a)

    comparisons: List[Dict[str, Any]] = []
    prefix = f"{project_b}::"

    for f in project_files:
        rel_path = f.get("relative_path", "")
        ftype = f.get("file_type", "")
        if not rel_path or not is_scannable(rel_path)[0]:
            continue
        fps = file_fingerprints.get(rel_path, [])
        if not fps or ftype not in ("code", "text"):
            continue

        fp_hashes = [h for h, _p in fps]
        total_a_fps = len(fp_hashes)
        if not total_a_fps:
            continue

        candidates = db.query_candidates(fp_hashes, ftype, project_a)

        for key, shared in candidates.items():
            # Restrict results STRICTLY to project_b.
            if not key.startswith(prefix):
                continue
            other_path = key[len(prefix):]
            if not is_scannable(other_path)[0]:
                continue

            total_b_fps = db.get_file_fingerprint_count(project_b, other_path)
            if not total_b_fps:
                continue

            # Overlap coefficient: shared / min(source, target)
            sim_val = min(shared / min(total_a_fps, total_b_fps), 1.0)
            if sim_val < 0.20:  # Filter out weak matches below 20%
                continue

            comparisons.append({
                "file_a": rel_path,
                "file_b": other_path,
                "similarity": round(sim_val * 100, 2),
                "type": ftype,
            })

    comparisons.sort(key=lambda c: c["similarity"], reverse=True)
    return comparisons


@router.post("/api/plagiarism/compare-projects", dependencies=[Depends(require_role())])
async def compare_projects(req: ProjectComparisonRequest):
    """Direct project-to-project comparison: overlap matrix of matching files."""
    project_a = (req.project_a or "").strip()
    project_b = (req.project_b or "").strip()
    if not project_a or not project_b:
        raise HTTPException(
            status_code=400,
            detail="Both 'project_a' and 'project_b' are required.",
        )
    if project_a == project_b:
        raise HTTPException(
            status_code=400,
            detail="'project_a' and 'project_b' must be different projects.",
        )

    db = get_db()
    if not db.get_project_by_id(project_a):
        raise HTTPException(status_code=404, detail=f"Project '{project_a}' not found in database")
    if not db.get_project_by_id(project_b):
        raise HTTPException(status_code=404, detail=f"Project '{project_b}' not found in database")

    try:
        comparisons = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_project_comparison(project_a, project_b)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project comparison failed: {str(e)}")

    return {
        "status": "completed",
        "project_a": project_a,
        "project_b": project_b,
        "match_count": len(comparisons),
        "comparisons": comparisons,
    }


class CompareFilesRequest(BaseModel):
    project_a: str
    file_a: str
    project_b: str
    file_b: str


def _resolve_stored_file(project_id: str, relative_path: str) -> Optional[str]:
    """Return the text content of one stored project file, or None if absent.

    Looks on disk first (``data/project_files/<project>/<relative_path>``) and
    then falls back to the database copy, which is where uploaded archives are
    actually kept by ``db.save_project()``. The resolved path is verified to stay
    inside the project folder so a crafted ``relative_path`` cannot escape it.
    """
    # --- 1. On-disk copy -----------------------------------------------------
    project_root = os.path.realpath(
        os.path.join(str(DATA_DIR), "project_files", project_id)
    )
    candidate = os.path.realpath(os.path.join(project_root, relative_path))
    if candidate.startswith(project_root + os.sep) and os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            pass

    # --- 2. Database copy (compressed project_files table) -------------------
    db = get_db()
    for f in db.get_project_files(project_id):
        if f.get("relative_path") == relative_path:
            return f.get("content", "") or ""
    return None


@router.post("/api/plagiarism/compare-files", dependencies=[Depends(require_role())])
async def compare_files_endpoint(req: CompareFilesRequest):
    """Line-level diff of two stored files, used by the visual Diff Viewer.

    Returns both files split into lines plus the raw ``difflib`` opcodes
    ``(tag, i1, i2, j1, j2)``; the frontend highlights every ``equal`` block
    because identical lines are the plagiarism evidence.
    """
    project_a = (req.project_a or "").strip()
    project_b = (req.project_b or "").strip()
    file_a = (req.file_a or "").strip()
    file_b = (req.file_b or "").strip()
    if not project_a or not project_b or not file_a or not file_b:
        raise HTTPException(
            status_code=400,
            detail="'project_a', 'file_a', 'project_b' and 'file_b' are all required.",
        )

    ok_a, reason_a = is_scannable(file_a)
    ok_b, reason_b = is_scannable(file_b)
    if not ok_a:
        raise HTTPException(status_code=400, detail=f"File '{file_a}' is not scannable ({reason_a}).")
    if not ok_b:
        raise HTTPException(status_code=400, detail=f"File '{file_b}' is not scannable ({reason_b}).")

    def _load() -> tuple:
        return (
            _resolve_stored_file(project_a, file_a),
            _resolve_stored_file(project_b, file_b),
        )

    content_a, content_b = await asyncio.get_event_loop().run_in_executor(None, _load)

    if content_a is None or content_b is None:
        missing = []
        if content_a is None:
            missing.append(f"'{file_a}' in project '{project_a}'")
        if content_b is None:
            missing.append(f"'{file_b}' in project '{project_b}'")
        raise HTTPException(404, f"One or both files not found on disk: {', '.join(missing)}")

    lines_a = content_a.splitlines()
    lines_b = content_b.splitlines()

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    opcodes = matcher.get_opcodes()  # list of tuples: (tag, i1, i2, j1, j2)
    matched_lines = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")

    return {
        "project_a": project_a,
        "project_b": project_b,
        "file_a": file_a,
        "file_b": file_b,
        "lines_a": lines_a,
        "lines_b": lines_b,
        "opcodes": opcodes,
        "matched_lines": matched_lines,
        "match_ratio": round(matcher.ratio() * 100, 2),
    }


@router.post("/api/plagiarism/compare-direct-files", dependencies=[Depends(require_role())])
async def compare_direct_files(
    file_a: Optional[UploadFile] = File(None),
    file_b: Optional[UploadFile] = File(None),
    project_a_id: Optional[str] = Form(None),
    file_a_path: Optional[str] = Form(None),
    project_b_id: Optional[str] = Form(None),
    file_b_path: Optional[str] = Form(None),
):
    """Direct pairwise comparison of any two documents or code files.

    Files may be provided as uploaded files (PDF, Word docx, Code, Text)
    OR selected from existing indexed database projects.
    Extracts text, computes hybrid similarity score (fusion/Winnowing),
    and performs line-level diffing for the visual Diff Viewer.
    """
    db = get_db()
    extractor = FileExtractor()

    def _resolve_file(upload: Optional[UploadFile], project_id: Optional[str], file_path: Optional[str], default_label: str) -> tuple[str, str, str]:
        if upload is not None and upload.filename:
            filename = upload.filename
            ext = Path(filename).suffix.lower()
            ftype = file_type_for(filename) or "text"
            content_bytes = upload.file.read()
            if not content_bytes:
                return "", ftype, filename

            if ext in (".pdf", ".docx"):
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(content_bytes)
                    tmp_path = tmp.name
                try:
                    if ext == ".pdf":
                        text = extractor.extract_text_from_pdf(tmp_path)
                    else:
                        text = extractor.extract_text_from_docx(tmp_path)
                    return text, "text", filename
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            else:
                text = content_bytes.decode("utf-8", errors="replace")
                return text, ftype, filename

        elif project_id and file_path:
            db_files = db.get_files_by_paths(project_id, [file_path])
            if not db_files:
                raise HTTPException(status_code=404, detail=f"File '{file_path}' not found in project '{project_id}'.")
            item = db_files[0]
            content = item.get("content", "")
            ftype = item.get("file_type") or file_type_for(file_path) or "text"
            label = f"{project_id} : {file_path}"
            return content, ftype, label

        raise HTTPException(status_code=400, detail=f"Missing file source for {default_label}: upload a file or select from database.")

    content_a, type_a, name_a = _resolve_file(file_a, project_a_id, file_a_path, "File A")
    content_b, type_b, name_b = _resolve_file(file_b, project_b_id, file_b_path, "File B")

    if not content_a.strip() or not content_b.strip():
        raise HTTPException(status_code=400, detail="One or both files contain no extractable text.")

    eff_type = "code" if (type_a == "code" or type_b == "code") else "text"
    winnow_engine = WinnowingEngine()

    fusion_result = compute_fusion_score(
        file_a_content=content_a,
        file_b_content=content_b,
        file_type=eff_type,
        winnowing_engine=winnow_engine,
        filename=name_a,
        filename_b=name_b,
    )

    lines_a = content_a.splitlines()
    lines_b = content_b.splitlines()

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    opcodes = matcher.get_opcodes()
    matched_lines = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")

    return {
        "file_a_name": name_a,
        "file_b_name": name_b,
        "file_type": eff_type,
        "similarity": fusion_result["fusion_score"],
        "winnowing_score": fusion_result["winnowing_score"],
        "semantic_score": fusion_result["semantic_score"],
        "containment_score": fusion_result["containment_score"],
        "verdict": fusion_result["verdict"],
        "lines_a": lines_a,
        "lines_b": lines_b,
        "opcodes": opcodes,
        "matched_lines": matched_lines,
        "match_ratio": round(matcher.ratio() * 100, 2),
        "total_lines_a": len(lines_a),
        "total_lines_b": len(lines_b),
    }
