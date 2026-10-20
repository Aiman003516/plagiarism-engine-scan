"""Project listing, update, approval, deletion, files and embedding indexing."""

import asyncio
from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel


from fastapi import APIRouter
from app.dependencies import require_role
from app.services.embeddings import _index_project_embeddings
from app.state import get_db, get_vstore

router = APIRouter(tags=["projects"])


@router.get("/api/plagiarism/projects", dependencies=[Depends(require_role())])
async def list_projects(limit: int = 1000, page: int = 1):
    db = get_db()
    loop = asyncio.get_running_loop()
    projects = await loop.run_in_executor(None, lambda: db.get_all_projects(page=page, limit=limit))

    # The Faculty Approval UI drives off `status`, and students may only see
    # their own submissions via `student_id`. Guarantee both keys exist on every
    # row (older rows predate the student_id column and may hold NULLs).
    serialized = []
    for project in projects:
        item = dict(project)
        if not item.get("status"):
            item["status"] = "approved"
        item.setdefault("student_id", None)
        serialized.append(item)

    return {"projects": serialized}


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    abstract: Optional[str] = None
    team_id: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None
    university: Optional[str] = None
    status: Optional[str] = None


@router.put("/api/plagiarism/projects/{project_id}", dependencies=[Depends(require_role())])
async def update_project(project_id: str, payload: ProjectUpdate):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    def _update():
        db.update_project(
            project_id,
            title=payload.title,
            abstract=payload.abstract,
            team_id=payload.team_id,
            department=payload.department,
            year=payload.year,
            university=payload.university,
            status=payload.status,
        )
        return db.get_project_by_id(project_id)

    updated = await loop.run_in_executor(None, _update)
    return updated


@router.post("/api/plagiarism/projects/{project_id}/approve", dependencies=[Depends(require_role("ministry_admin", "college_admin", "faculty"))])
async def approve_project(project_id: str):
    """Faculty approval workflow: flip a pending project's status to 'approved'."""
    db = get_db()
    loop = asyncio.get_running_loop()

    def _approve():
        conn = db._get_connection()
        try:
            cursor = conn.cursor()
            placeholder = "%s" if db.mode == "postgresql" else "?"
            cursor.execute(f"UPDATE projects SET status = 'approved' WHERE id = {placeholder}", (project_id,))
            if cursor.rowcount == 0:
                conn.rollback()
                raise HTTPException(404, "Project not found")
            conn.commit()
        finally:
            conn.close()

    await loop.run_in_executor(None, _approve)
    return {"detail": "Project approved successfully"}


@router.delete("/api/plagiarism/projects/{project_id}", dependencies=[Depends(require_role())])
async def delete_project(project_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    await loop.run_in_executor(None, lambda: db.delete_project(project_id))

    # Clean up the project's embeddings from the Postgres vector store as well.
    try:
        vstore = get_vstore()
        await loop.run_in_executor(
            None, lambda: vstore.delete_project(project_id)
        )
    except Exception as e:
        print(f"Postgres vector cleanup warning for project '{project_id}': {e}")

    return {"detail": "Project deleted"}


@router.get("/api/plagiarism/projects/{project_id}/files", dependencies=[Depends(require_role())])
async def list_project_files(project_id: str, include_content: bool = False):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    files = await loop.run_in_executor(
        None, lambda: db.get_project_files(project_id, include_content=include_content)
    )
    return {"files": files}

@router.post("/api/plagiarism/projects/{project_id}/index-embeddings")
async def index_project_embeddings(project_id: str, user=Depends(require_role("ministry_admin", "college_admin", "faculty"))):
    """On-demand Deep Scan indexer: generate a project's embeddings and store them in PostgreSQL.

    Uploads no longer build the vector index (see ``_run_intake``), so this
    endpoint populates it explicitly. Safe to call repeatedly — stale vectors
    for the project are replaced, never duplicated.
    """
    pid = (project_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Missing 'project_id' in the request path.")

    db_store = get_db()
    if not db_store.get_project_by_id(pid):
        raise HTTPException(status_code=404, detail=f"Project '{pid}' not found in database")

    vstore = get_vstore()
    print(
        f"[Postgres Vector] Embedding indexing requested for project '{pid}' "
        f"by {user.get('role')} '{user.get('user_id')}'..."
    )

    try:
        # Encoding is heavy (minutes on large projects): keep it on a worker
        # thread so the event loop stays responsive.
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: _index_project_embeddings(vstore, db_store, pid, log_callback=print)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding indexing failed for project '{pid}': {str(e)}",
        )

    return {"status": "indexed", "project_id": pid}


@router.get("/api/plagiarism/projects/check")
async def check_projects(names: str):
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.check_project_exists(name_list))
    return existing



class SemanticSearchRequest(BaseModel):
    query: str
    threshold: Optional[float] = 0.15
    top_k: Optional[int] = 20
    department: Optional[str] = None
    year: Optional[int] = None
    university: Optional[str] = None


@router.post("/api/plagiarism/projects/semantic-search", dependencies=[Depends(require_role())])
async def semantic_project_search(payload: SemanticSearchRequest):
    """
    AI Semantic Proposal / Abstract Search (Spec Step 2.A).
    Accepts student project titles, problem statements, or proposed abstracts in English or Arabic,
    generates 1024-dim dense embeddings via BAAI/bge-m3, and matches them against project documentation
    and abstracts in pgvector. Returns ranked project records with cosine similarity percentages.
    """
    query = (payload.query or "").strip()
    if not query:
        return {
            "query": "",
            "model_used": "bge-m3",
            "total_found": 0,
            "projects": [],
        }

    db = get_db()
    loop = asyncio.get_running_loop()

    def _search():
        import numpy as np
        from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
        from plagiarism_engine.vectors.pgvector_store import PgVectorStore, _calibrate

        model, model_name = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
        if model is None:
            raise HTTPException(status_code=500, detail="Semantic search model is currently loading.")

        raw_q_emb = model.encode(query, convert_to_numpy=True)
        q_emb = PgVectorStore._normalize_and_pad_1d(raw_q_emb, 1024)

        conn = db._get_connection()
        try:
            cur = conn.cursor()
            sql = """
                SELECT pf.project_id, pf.relative_path, pf.embedding, pf.embedding_model,
                       p.name, p.title, p.abstract, p.department, p.year, p.university, p.status
                FROM project_files pf
                JOIN projects p ON p.id = pf.project_id
                WHERE pf.file_type = 'text' AND pf.embedding IS NOT NULL
            """
            params = []
            if payload.department:
                sql += " AND LOWER(p.department) = LOWER(%s)"
                params.append(payload.department)
            if payload.year:
                sql += " AND p.year = %s"
                params.append(payload.year)
            if payload.university:
                sql += " AND LOWER(p.university) LIKE LOWER(%s)"
                params.append(f"%{payload.university}%")

            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

            project_hits = {}
            for r in rows:
                pid = r[0]
                rel_path = r[1]
                emb_raw = r[2]
                emb_model = r[3]
                name = r[4]
                title = r[5] or name
                abstract = r[6]
                dept = r[7]
                yr = r[8]
                uni = r[9]
                status = r[10] or "approved"

                emb = PgVectorStore._parse_embedding(emb_raw)
                if emb is None:
                    continue

                sim = float(np.dot(q_emb, emb))
                calibrated_sim = _calibrate(sim, emb_model)

                if pid not in project_hits or calibrated_sim > project_hits[pid]["similarity"]:
                    project_hits[pid] = {
                        "project_id": pid,
                        "name": name,
                        "title": title,
                        "abstract": abstract,
                        "department": dept,
                        "year": yr,
                        "university": uni,
                        "status": status,
                        "similarity": round(calibrated_sim, 4),
                        "similarity_raw": round(sim, 4),
                        "similarity_percent": round(calibrated_sim * 100, 1),
                        "top_matching_file": rel_path,
                        "embedding_model": emb_model or model_name,
                    }

            # Also check projects with abstracts in the projects table
            cur.execute(
                "SELECT id, name, title, abstract, department, year, university, status FROM projects WHERE abstract IS NOT NULL AND TRIM(abstract) != ''"
            )
            for r in cur.fetchall():
                pid = r[0]
                if pid in project_hits and project_hits[pid]["similarity"] >= 0.70:
                    continue
                abs_text = (r[3] or "").strip()
                if not abs_text:
                    continue
                abs_emb = model.encode(abs_text[:2000], convert_to_numpy=True)
                abs_emb = PgVectorStore._normalize_and_pad_1d(abs_emb, 1024)
                sim = float(np.dot(q_emb, abs_emb))
                calibrated_sim = _calibrate(sim, model_name)
                if pid not in project_hits or calibrated_sim > project_hits[pid]["similarity"]:
                    project_hits[pid] = {
                        "project_id": pid,
                        "name": r[1],
                        "title": r[2] or r[1],
                        "abstract": abs_text,
                        "department": r[4],
                        "year": r[5],
                        "university": r[6],
                        "status": r[7] or "approved",
                        "similarity": round(calibrated_sim, 4),
                        "similarity_raw": round(sim, 4),
                        "similarity_percent": round(calibrated_sim * 100, 1),
                        "top_matching_file": "project_abstract",
                        "embedding_model": model_name,
                    }

            thresh = payload.threshold if payload.threshold is not None else 0.15
            filtered = [p for p in project_hits.values() if p["similarity"] >= thresh]
            filtered.sort(key=lambda x: x["similarity"], reverse=True)
            top_k = payload.top_k or 20

            return {
                "query": query,
                "model_used": model_name or "bge-m3",
                "total_found": len(filtered),
                "projects": filtered[:top_k],
            }
        finally:
            conn.close()

    return await loop.run_in_executor(None, _search)
