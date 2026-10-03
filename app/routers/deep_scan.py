"""AI deep scan endpoints (single and bulk)."""

import asyncio
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel


from fastapi import APIRouter
from app.dependencies import require_role
from app.services.embeddings import _index_project_embeddings
from app.state import _get_deep_scan_model, get_db, get_vstore

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
    model_name = "unixcoder-base" if file_type == "code" else "bge-m3"
    try:
        model = _get_deep_scan_model(model_name)
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: model.encode(
                [content1, content2],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        )
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="SentenceTransformer model is not downloaded yet. Please wait.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep scan failed: {str(e)}")

    similarity_pct = round(similarity * 100, 2)
    verdict = "CONFIRMED_PLAGIARISM" if similarity > 0.85 else "LIKELY_ORIGINAL"

    return {
        "ai_similarity": similarity_pct,
        "model_used": model_name,
        "method": "cosine_similarity",
        "verdict": verdict,
        "file1": req.file1_path,
        "file2": req.file2_path,
    }


class BulkDeepScanRequest(BaseModel):
    project_id: str


@router.post("/api/plagiarism/deep-scan-bulk", dependencies=[Depends(require_role())])
async def deep_scan_bulk(req: BulkDeepScanRequest):
    """FAISS bulk semantic scan: top-5 cross-project matches for every file of a project."""
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

    # Embedding generation is decoupled from the upload stream, so a project
    # that was never deep-indexed holds ZERO vectors and search_bulk() would
    # silently return an empty result. Build the index on demand first so Deep
    # Scan always works, even when the user never indexed manually.
    try:
        if vstore.count_project_vectors(project_id) == 0:
            print(
                f"[FAISS] Project '{project_id}' has no vectors yet; "
                f"auto-indexing before bulk deep scan..."
            )
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: _index_project_embeddings(vstore, db, project_id)
            )
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
