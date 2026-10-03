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
async def list_projects():
    db = get_db()
    projects = db.get_all_projects()

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
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
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


@router.post("/api/plagiarism/projects/{project_id}/approve", dependencies=[Depends(require_role("ministry_admin", "college_admin", "faculty"))])
async def approve_project(project_id: str):
    """Faculty approval workflow: flip a pending project's status to 'approved'."""
    db = get_db()
    conn = db._get_connection()
    try:
        cursor = conn.cursor()
        # psycopg2 and sqlite3 use different parameter placeholders.
        placeholder = "%s" if db.mode == "postgresql" else "?"
        cursor.execute(f"UPDATE projects SET status = 'approved' WHERE id = {placeholder}", (project_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            raise HTTPException(404, "Project not found")
        conn.commit()
    finally:
        conn.close()
    return {"detail": "Project approved successfully"}


@router.delete("/api/plagiarism/projects/{project_id}", dependencies=[Depends(require_role())])
async def delete_project(project_id: str):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete_project(project_id)

    # Clean up the project's embeddings from the FAISS vector store as well.
    # Runs in an executor so index I/O never blocks the event loop; a failure
    # here must not fail the (already completed) DB deletion.
    try:
        vstore = get_vstore()
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: vstore.delete_project(project_id)
        )
    except Exception as e:
        print(f"FAISS cleanup warning for project '{project_id}': {e}")

    return {"detail": "Project deleted"}


@router.get("/api/plagiarism/projects/{project_id}/files", dependencies=[Depends(require_role())])
async def list_project_files(project_id: str):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    files = db.get_project_files(project_id)
    return {"files": files}

@router.post("/api/plagiarism/projects/{project_id}/index-embeddings")
async def index_project_embeddings(project_id: str, user=Depends(require_role("ministry_admin", "college_admin", "faculty"))):
    """On-demand Deep Scan indexer: generate a project's embeddings and add them to FAISS.

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
        f"[FAISS] Embedding indexing requested for project '{pid}' "
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
    existing = db.check_project_exists(name_list)
    return existing
