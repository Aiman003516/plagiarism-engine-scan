"""AI deep scan endpoints (single and bulk)."""

import asyncio
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel


from fastapi import APIRouter
from app.dependencies import require_role
from app.services.embeddings import _index_project_embeddings
from app.state import get_db, get_vstore

router = APIRouter(tags=["deep-scan"])


class DeepScanRequest(BaseModel):
    # `project_id` is the baseline (source) project the report was produced from.
    # `project_name` / `target` are accepted as aliases so callers that only know
    # the project name (e.g. a report loaded from history) still work.
    project_id: Optional[str] = None
    file1_path: str
    other_project_id: Optional[str] = None
    file2_path: str
    project_name: Optional[str] = None
    target: Optional[str] = None


def _cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two 1-D vectors using numpy."""
    import numpy as np

    a = np.asarray(a, dtype="float32").flatten()
    b = np.asarray(b, dtype="float32").flatten()
    denom = (float(np.linalg.norm(a) * np.linalg.norm(b))) or 1.0
    return float(np.dot(a, b) / denom)


def _resolve_file_type(relative_path: str) -> str:
    """Return 'code' or 'text' based on the file extension."""
    from plagiarism_engine.extractor import CODE_EXTENSIONS

    ext = Path(relative_path).suffix.lower()
    return "code" if ext in CODE_EXTENSIONS else "text"


@router.post("/api/plagiarism/deep-scan", dependencies=[Depends(require_role())])
async def deep_scan(req: DeepScanRequest):
    db = get_db()

    # --- 0. Resolve the baseline project id from the JSON payload -----------
    project_id = (req.project_id or req.project_name or req.target or "").strip()
    other_project_id = (req.other_project_id or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'project_id' (the baseline project) in the request payload.",
        )
    if not other_project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'other_project_id' (the matched project) in the request payload.",
        )
    if not req.file1_path or not req.file2_path:
        raise HTTPException(
            status_code=400,
            detail="Both 'file1_path' and 'file2_path' are required.",
        )

    # --- 1. Load both files' content from the database ----------------------
    files1 = db.get_project_files(project_id)
    files2 = db.get_project_files(other_project_id)

    if not files1:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found in database")
    if not files2:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{other_project_id}' not found in database",
        )

    file1 = next((f for f in files1 if f.get("relative_path") == req.file1_path), None)
    file2 = next((f for f in files2 if f.get("relative_path") == req.file2_path), None)

    if file1 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file1_path}' not found in project '{project_id}'",
        )
    if file2 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file2_path}' not found in project '{other_project_id}'",
        )

    content1 = file1.get("content", "") or ""
    content2 = file2.get("content", "") or ""
    if not content1.strip() or not content2.strip():
        raise HTTPException(status_code=400, detail="Both files must have non-empty content")

    # --- 2. Determine file type by extension --------------------------------
    # Use the stored file_type when present; otherwise derive from extension.
    ftype1 = file1.get("file_type") or _resolve_file_type(req.file1_path)
    ftype2 = file2.get("file_type") or _resolve_file_type(req.file2_path)

    # Use the first file's type to pick the model. If the two disagreed, base
    # the choice on the pair's dominant type (code wins only when both are code).
    if ftype1 == "code" and ftype2 == "code":
        file_type = "code"
    else:
        file_type = "text"

    # --- 3/4. Load model + encode + compute cosine similarity --------------
    # Same model selection, calibration and verdict scale as the hybrid pipeline.
    from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
    from plagiarism_engine.fusion_scorer import calibrate_semantic, verdict_for

    model, model_name = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS[file_type])
    if model is None:
        raise HTTPException(status_code=503, detail="SentenceTransformer model is not downloaded yet. Please wait.")
    try:
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: model.encode(
                [content1[:4000], content2[:4000]],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        )
        raw_similarity = _cosine_similarity(embeddings[0], embeddings[1])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep scan failed: {str(e)}")

    calibrated = calibrate_semantic(raw_similarity, model_name)

    return {
        "ai_similarity": round(calibrated * 100, 2),
        "ai_similarity_raw": round(raw_similarity * 100, 2),
        "model_used": model_name,
        "method": "cosine_similarity_calibrated",
        "verdict": verdict_for(calibrated),
        "file1": req.file1_path,
        "file2": req.file2_path,
    }


class BulkDeepScanRequest(BaseModel):
    project_id: str


@router.post("/api/plagiarism/deep-scan-bulk", dependencies=[Depends(require_role())])
async def deep_scan_bulk(req: BulkDeepScanRequest):
    """Postgres 2-Step Rescoring bulk semantic scan: top-5 cross-project matches for every file of a project."""
    project_id = (req.project_id or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'project_id' in the request payload.",
        )

    db = get_db()
    if not db.get_project_by_id(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found in database",
        )

    vstore = get_vstore()

    # Embedding generation is decoupled from the upload stream, so projects
    # that were never deep-indexed hold ZERO vectors. Build the index on demand
    # for the target project (and any unindexed recent corpus projects) so Deep
    # Scan always works even when the user never indexed manually.
    def _ensure_indexed():
        pids = [project_id]
        for proj in db.get_all_projects(limit=50):
            pid = proj.get("id") or proj.get("name")
            if pid and pid not in pids:
                pids.append(pid)
        for pid in pids:
            try:
                if vstore.needs_reindex(pid):
                    print(
                        f"[Postgres Vector] Project '{pid}' has missing or stale vectors; "
                        f"re-indexing before bulk deep scan..."
                    )
                    _index_project_embeddings(vstore, db, pid)
            except Exception as e:
                if pid == project_id:
                    raise
                print(f"[Postgres Vector] Skipping corpus project '{pid}' (indexing failed: {e})")

    try:
        await asyncio.get_event_loop().run_in_executor(None, _ensure_indexed)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Deep scan auto-indexing failed for project '{project_id}': {str(e)}",
        )

    try:
        matches = await asyncio.get_event_loop().run_in_executor(
            None, lambda: vstore.search_bulk(project_id)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk deep scan failed: {str(e)}")

    return {
        "project_id": project_id,
        "match_count": len(matches),
        "matches": matches,
    }
