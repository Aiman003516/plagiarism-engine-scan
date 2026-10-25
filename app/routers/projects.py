"""Project listing, update, approval, deletion, files and embedding indexing."""

import asyncio
from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel


from fastapi import APIRouter
from app.dependencies import require_role
from app.services.embeddings import _index_project_embeddings
from app.state import get_db, get_vstore
from plagiarism_engine.db.helpers import decompress_text

router = APIRouter(tags=["projects"])


@router.get("/api/plagiarism/projects")
async def list_projects(limit: int = 1000, page: int = 1, current_user: dict = Depends(require_role())):
    db = get_db()
    loop = asyncio.get_running_loop()
    projects = await loop.run_in_executor(None, lambda: db.get_all_projects(page=page, limit=limit))

    serialized = []
    caller_role = current_user.get("role")
    caller_id = current_user.get("user_id")

    caller_record = {}
    if caller_role == "student":
        caller_record = await loop.run_in_executor(None, lambda: db.get_student_by_id(caller_id)) or {}
    else:
        caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}

    caller_college = caller_record.get("college_id")
    caller_uni = caller_record.get("university_id")
    caller_team = caller_record.get("team_id")

    for project in projects:
        item = dict(project)
        if not item.get("status"):
            item["status"] = "approved"
        item.setdefault("student_id", None)

        proj_status = item.get("status")
        proj_college = item.get("college_id")
        proj_uni = item.get("university_id")

        if caller_role == "student":
            is_author = (item.get("student_id") == caller_id or item.get("submitted_by_student_id") == caller_id)
            is_teammate = bool(caller_team and item.get("team_id") == caller_team)
            if not (is_author or is_teammate):
                continue

        elif caller_role in ("college_admin", "faculty"):
            if proj_status in ("pending_review", "rejected"):
                if caller_college and proj_college and proj_college != caller_college:
                    continue
            elif caller_college and proj_college and proj_college != caller_college:
                continue

        elif caller_role == "university_admin":
            if proj_status in ("pending_review", "rejected"):
                if caller_uni and proj_uni and proj_uni != caller_uni:
                    continue
            elif caller_uni and proj_uni and proj_uni != caller_uni:
                continue

        if item.get("abstract"):
            item["abstract"] = decompress_text(item["abstract"])

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


@router.put("/api/plagiarism/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, current_user: dict = Depends(require_role())):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    caller_role = current_user.get("role")
    caller_id = current_user.get("user_id")
    if caller_role == "student":
        if existing.get("student_id") != caller_id and existing.get("submitted_by_student_id") != caller_id:
            raise HTTPException(status_code=403, detail="You can only edit your own project.")
        if existing.get("status") in ("approved", "rejected"):
            raise HTTPException(status_code=403, detail="Cannot edit proposal once it has been approved or rejected. Contact your supervisor to request changes.")
        if payload.status and payload.status != "pending_review":
            raise HTTPException(status_code=403, detail="Students cannot alter project status.")
    elif caller_role in ("college_admin", "faculty"):
        caller_rec = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}
        caller_college = caller_rec.get("college_id")
        if caller_college and existing.get("college_id") and existing.get("college_id") != caller_college:
            raise HTTPException(status_code=403, detail="Cannot edit projects belonging to another college.")
    elif caller_role == "university_admin":
        caller_rec = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}
        caller_uni = caller_rec.get("university_id")
        if caller_uni and existing.get("university_id") and existing.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Cannot edit projects belonging to another university.")

    def _update():
        fields = {
            "title": payload.title,
            "abstract": payload.abstract,
            "team_id": payload.team_id,
            "department": payload.department,
            "year": payload.year,
            "university": payload.university,
            "status": payload.status,
        }
        if payload.abstract and payload.abstract.strip():
            try:
                import json
                from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
                from plagiarism_engine.vectors.pgvector_store import PgVectorStore
                from plagiarism_engine.text_detector import normalize_arabic_text
                model, _ = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
                if model:
                    norm = normalize_arabic_text(payload.abstract.strip()[:1500])
                    raw = model.encode(norm, convert_to_numpy=True)
                    pv = PgVectorStore(db)
                    emb_1024 = pv._normalize_and_pad_1d(raw, 1024)
                    fields["abstract_embedding"] = json.dumps(emb_1024.tolist())
                    fields["abstract_embedding_binary"] = pv._quantize_to_bit_string(emb_1024)
            except Exception as e:
                print("Warning on abstract re-embed:", e)

        db.update_project(project_id, **fields)
        return db.get_project_by_id(project_id)

    updated = await loop.run_in_executor(None, _update)
    return updated


@router.post("/api/plagiarism/projects/{project_id}/approve")
async def approve_project(project_id: str, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    """Faculty approval workflow: flip a pending project's status to 'approved'."""
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    caller_role = current_user.get("role")
    caller_rec = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}
    if caller_role in ("college_admin", "faculty"):
        caller_college = caller_rec.get("college_id")
        if caller_college and existing.get("college_id") and existing.get("college_id") != caller_college:
            raise HTTPException(status_code=403, detail="Cannot approve projects belonging to another college.")
    elif caller_role == "university_admin":
        caller_uni = caller_rec.get("university_id")
        if caller_uni and existing.get("university_id") and existing.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Cannot approve projects belonging to another university.")

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


class StudentSubmitRequest(BaseModel):
    title: str
    abstract: str
    department: Optional[str] = None
    year: Optional[int] = None
    university: Optional[str] = None


class ProjectReviewRequest(BaseModel):
    action: str  # 'approve' | 'reject'
    notes: Optional[str] = None
    reopen_submission: Optional[bool] = False


@router.post("/api/plagiarism/projects/student-submit", dependencies=[Depends(require_role("student"))])
async def student_submit_proposal(payload: StudentSubmitRequest, current_user: dict = Depends(require_role("student"))):
    """
    Allow a student to submit their graduation proposal if their assigned team
    has been granted a one-time submission token by their academic supervisor.
    """
    db = get_db()
    loop = asyncio.get_running_loop()
    student_id = current_user.get("user_id")

    def _submit():
        student = db.get_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found.")

        team_id = student.get("team_id")
        if not team_id:
            raise HTTPException(
                status_code=400,
                detail="You must be a member of a team to submit a proposal. Please join or create a team first."
            )

        team = db.get_team_by_id(team_id)
        if not team or not team.get("submission_allowed"):
            raise HTTPException(
                status_code=403,
                detail="Proposal submission is locked for your team. Please request submission authorization from your faculty supervisor / department head."
            )

        title = payload.title.strip()
        abstract = payload.abstract.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Project title is required.")
        if not abstract:
            raise HTTPException(status_code=400, detail="Proposal abstract / problem statement is required.")

        import uuid
        from datetime import datetime
        project_id = str(uuid.uuid4())

        # 1. Store base project
        db.save_project(project_id, title, [])

        # 2. Update with academic metadata and student attribution
        dept = payload.department or student.get("department_id") or "Artificial Intelligence"
        yr = payload.year or datetime.now().year
        uni = payload.university or student.get("university") or "Sana'a University"

        fields = {
            "title": title,
            "abstract": abstract,
            "team_id": team_id,
            "department": dept,
            "year": yr,
            "university": uni,
            "status": "pending_review",
            "student_id": student_id,
            "submitted_by_student_id": student_id,
            "university_id": student.get("university_id"),
            "college_id": student.get("college_id"),
            "department_id": student.get("department_id"),
        }

        # 3. Generate immediate abstract embedding for search
        try:
            import json
            from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
            from plagiarism_engine.vectors.pgvector_store import PgVectorStore
            from plagiarism_engine.text_detector import normalize_arabic_text
            model, _ = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
            if model:
                norm = normalize_arabic_text(abstract[:1500])
                raw = model.encode(norm, convert_to_numpy=True)
                pv = PgVectorStore(db)
                emb_1024 = pv._normalize_and_pad_1d(raw, 1024)
                fields["abstract_embedding"] = json.dumps(emb_1024.tolist())
                fields["abstract_embedding_binary"] = pv._quantize_to_bit_string(emb_1024)
        except Exception as e:
            print("Warning generating abstract embedding for student submission:", e)

        db.update_project(project_id, **fields)

        # 4. Consume the one-time submission token
        db.update_team(team_id, submission_allowed=False)

        return db.get_project_by_id(project_id)

    return await loop.run_in_executor(None, _submit)


@router.post("/api/plagiarism/projects/{project_id}/review")
async def review_project(project_id: str, payload: ProjectReviewRequest, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    """
    Supervisor / Committee Review:
    - Approve proposal (`action='approve'`)
    - Reject proposal (`action='reject'`) with review notes and optional one-time re-open.
    """
    db = get_db()
    loop = asyncio.get_running_loop()

    def _review():
        existing = db.get_project_by_id(project_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        if caller_role in ("college_admin", "faculty"):
            caller_college = caller_record.get("college_id")
            proj_college = existing.get("college_id")
            if proj_college and caller_college and proj_college != caller_college:
                raise HTTPException(status_code=403, detail="Cannot review proposals belonging to another college.")
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            proj_uni = existing.get("university_id")
            if proj_uni and caller_uni and proj_uni != caller_uni:
                raise HTTPException(status_code=403, detail="Cannot review proposals belonging to another university.")

        action = (payload.action or "").strip().lower()
        if action not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="Action must be either 'approve' or 'reject'.")

        new_status = "approved" if action == "approve" else "rejected"
        fields = {
            "status": new_status,
            "review_notes": (payload.notes or "").strip(),
        }
        db.update_project(project_id, **fields)

        # If rejected and supervisor allowed re-submission, re-open team's one-time token
        if action == "reject" and payload.reopen_submission:
            team_id = existing.get("team_id")
            if team_id:
                db.update_team(team_id, submission_allowed=True)

        return db.get_project_by_id(project_id)

    return await loop.run_in_executor(None, _review)


@router.delete("/api/plagiarism/projects/{project_id}")
async def delete_project(project_id: str, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin"))):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}
    if caller_role == "college_admin":
        caller_college = caller_record.get("college_id")
        if existing.get("college_id") and caller_college and existing.get("college_id") != caller_college:
            raise HTTPException(status_code=403, detail="Insufficient permissions to delete a project from another college.")
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        if existing.get("university_id") and caller_uni and existing.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Insufficient permissions to delete a project from another university.")

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


@router.get("/api/plagiarism/projects/{project_id}/files")
async def list_project_files(project_id: str, include_content: bool = False, current_user: dict = Depends(require_role())):
    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_project_by_id(project_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    if include_content:
        caller_role = current_user.get("role")
        caller_id = current_user.get("user_id")
        if caller_role == "student":
            student_rec = await loop.run_in_executor(None, lambda: db.get_student_by_id(caller_id)) or {}
            caller_team = student_rec.get("team_id")
            is_author = (existing.get("student_id") == caller_id or existing.get("submitted_by_student_id") == caller_id)
            is_teammate = bool(caller_team and existing.get("team_id") == caller_team)
            if not (is_author or is_teammate):
                raise HTTPException(status_code=403, detail="Students cannot download code files of other projects.")
        elif caller_role in ("college_admin", "faculty"):
            caller_rec = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}
            caller_col = caller_rec.get("college_id")
            if caller_col and existing.get("college_id") and existing.get("college_id") != caller_col:
                if existing.get("status") == "pending_review":
                    raise HTTPException(status_code=403, detail="Cannot access confidential proposal files from another college.")
        elif caller_role == "university_admin":
            caller_rec = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}
            caller_uni = caller_rec.get("university_id")
            if caller_uni and existing.get("university_id") and existing.get("university_id") != caller_uni:
                if existing.get("status") == "pending_review":
                    raise HTTPException(status_code=403, detail="Cannot access confidential proposal files from another university.")

    files = await loop.run_in_executor(
        None, lambda: db.get_project_files(project_id, include_content=include_content)
    )
    return {"files": files}

@router.post("/api/plagiarism/projects/{project_id}/index-embeddings")
async def index_project_embeddings(project_id: str, user=Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    """On-demand Deep Scan indexer: generate a project's embeddings and store them in PostgreSQL.

    Uploads no longer build the vector index (see ``_run_intake``), so this
    endpoint populates it explicitly. Safe to call repeatedly — stale vectors
    for the project are replaced, never duplicated.
    """
    pid = (project_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Missing 'project_id' in the request path.")

    db_store = get_db()
    proj = db_store.get_project_by_id(pid)
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project '{pid}' not found in database")

    caller_role = user.get("role")
    if caller_role in ("college_admin", "faculty"):
        caller_rec = db_store.get_user_by_id(user.get("user_id")) or {}
        caller_col = caller_rec.get("college_id")
        if caller_col and proj.get("college_id") and proj.get("college_id") != caller_col:
            raise HTTPException(status_code=403, detail="Cannot index embeddings for a project from another college.")
    elif caller_role == "university_admin":
        caller_rec = db_store.get_user_by_id(user.get("user_id")) or {}
        caller_uni = caller_rec.get("university_id")
        if caller_uni and proj.get("university_id") and proj.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Cannot index embeddings for a project from another university.")

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
async def check_projects(names: str, current_user: dict = Depends(require_role())):
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
        import re
        from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
        from plagiarism_engine.vectors.pgvector_store import PgVectorStore
        from plagiarism_engine.text_detector import normalize_arabic_text

        model, model_name = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
        if model is None:
            raise HTTPException(status_code=500, detail="Semantic search model is currently loading.")

        norm_query = normalize_arabic_text(query).lower()
        query_words = [w for w in re.findall(r'[\w\u0600-\u06FF]+', norm_query) if len(w) > 1]

        raw_q_emb = model.encode(norm_query, convert_to_numpy=True)
        q_emb = PgVectorStore._normalize_and_pad_1d(raw_q_emb, 1024)

        conn = db._get_connection()
        try:
            cur = conn.cursor()
            project_hits = {}

            # Helper for lexical token matching score (exact word-boundary token matching)
            def _calc_lexical_score(text_corpus: str) -> float:
                if not text_corpus or not query_words:
                    return 0.0
                norm_corpus = normalize_arabic_text(text_corpus).lower()
                corpus_words = set(re.findall(r'[\w\u0600-\u06FF]+', norm_corpus))
                hits = sum(1 for w in query_words if w in corpus_words)
                return min(1.0, hits / max(1, len(query_words)))

            # 1. Match against pre-computed project abstract embeddings and metadata
            # Only match approved projects to protect confidential unapproved proposals
            sql_p = """
                SELECT id, name, title, abstract, department, year, university, status, abstract_embedding, review_notes
                FROM projects
                WHERE (status NOT IN ('pending', 'pending_review', 'rejected') OR status IS NULL)
            """
            params_p = []
            if payload.department:
                sql_p += " AND LOWER(department) = LOWER(%s)"
                params_p.append(payload.department)
            if payload.year:
                sql_p += " AND year = %s"
                params_p.append(payload.year)
            if payload.university:
                sql_p += " AND LOWER(university) LIKE LOWER(%s)"
                params_p.append(f"%{payload.university}%")

            cur.execute(sql_p, tuple(params_p))
            for r in cur.fetchall():
                pid = r[0]
                name = r[1]
                title = r[2] or name
                abstract = decompress_text(r[3]) if r[3] else ""
                dept = r[4]
                yr = r[5]
                uni = r[6]
                status = r[7] or "approved"
                emb_raw = r[8]
                review_notes = r[9] if len(r) > 9 else None

                # 1. Lexical match score against title, abstract and department
                combined_corpus = f"{title} {name} {abstract} {dept or ''}"
                lex_score = _calc_lexical_score(combined_corpus)

                # 2. Dense semantic score
                sem_score = 0.0
                raw_cosine = 0.0
                if emb_raw:
                    emb = PgVectorStore._parse_embedding(emb_raw)
                    if emb is not None:
                        raw_cosine = float(np.dot(q_emb, emb))
                        # For short query proposal search, scale cosine smoothly without the 0.72 drop-to-zero wall:
                        sem_score = max(0.0, min(1.0, (raw_cosine - 0.35) / 0.55))

                # Hybrid fusion score
                if sem_score > 0 and lex_score > 0:
                    hybrid_score = 0.45 * lex_score + 0.55 * sem_score
                elif sem_score > 0:
                    words_in_q = len(norm_query.split())
                    if words_in_q < 5:
                        hybrid_score = sem_score * 0.50
                    else:
                        hybrid_score = sem_score * 0.75
                else:
                    hybrid_score = lex_score * 0.85

                # Exact title / name match bonus
                if norm_query in normalize_arabic_text(title).lower() or norm_query in normalize_arabic_text(name).lower():
                    hybrid_score = min(1.0, hybrid_score + 0.25)

                if hybrid_score > 0.05:
                    project_hits[pid] = {
                        "project_id": pid,
                        "name": name,
                        "title": title,
                        "abstract": abstract,
                        "department": dept,
                        "year": yr,
                        "university": uni,
                        "status": status,
                        "similarity": round(hybrid_score, 4),
                        "similarity_raw": round(raw_cosine, 4),
                        "similarity_percent": round(hybrid_score * 100, 1),
                        "lexical_score": round(lex_score, 3),
                        "top_matching_file": "project_abstract",
                        "embedding_model": model_name,
                    }

            # 2. Match against project documentation files with pre-stored embeddings
            sql_files = """
                SELECT pf.project_id, pf.relative_path, pf.embedding, pf.embedding_model,
                       p.name, p.title, p.abstract, p.department, p.year, p.university, p.status
                FROM project_files pf
                JOIN projects p ON p.id = pf.project_id
                WHERE pf.file_type = 'text' AND pf.embedding IS NOT NULL
                  AND (p.status NOT IN ('pending', 'pending_review', 'rejected') OR p.status IS NULL)
            """
            params_f = []
            if payload.department:
                sql_files += " AND LOWER(p.department) = LOWER(%s)"
                params_f.append(payload.department)
            if payload.year:
                sql_files += " AND p.year = %s"
                params_f.append(payload.year)
            if payload.university:
                sql_files += " AND LOWER(p.university) LIKE LOWER(%s)"
                params_f.append(f"%{payload.university}%")

            cur.execute(sql_files, tuple(params_f))
            for r in cur.fetchall():
                pid = r[0]
                rel_path = r[1]
                emb_raw = r[2]
                emb_model = r[3]
                name = r[4]
                title = r[5] or name
                abstract = decompress_text(r[6]) if r[6] else ""
                dept = r[7]
                yr = r[8]
                uni = r[9]
                status = r[10] or "approved"

                emb = PgVectorStore._parse_embedding(emb_raw)
                if emb is None:
                    continue

                raw_cosine = float(np.dot(q_emb, emb))
                sem_score = max(0.0, min(1.0, (raw_cosine - 0.35) / 0.55))

                combined_corpus = f"{title} {name} {abstract} {rel_path}"
                lex_score = _calc_lexical_score(combined_corpus)

                if sem_score > 0 and lex_score > 0:
                    hybrid_score = 0.45 * lex_score + 0.55 * sem_score
                elif sem_score > 0:
                    words_in_q = len(norm_query.split())
                    if words_in_q < 5:
                        hybrid_score = sem_score * 0.50
                    else:
                        hybrid_score = sem_score * 0.75
                else:
                    hybrid_score = lex_score * 0.85

                if pid not in project_hits or hybrid_score > project_hits[pid]["similarity"]:
                    if hybrid_score > 0.05:
                        project_hits[pid] = {
                            "project_id": pid,
                            "name": name,
                            "title": title,
                            "abstract": abstract or project_hits.get(pid, {}).get("abstract"),
                            "department": dept,
                            "year": yr,
                            "university": uni,
                            "status": status,
                            "similarity": round(hybrid_score, 4),
                            "similarity_raw": round(raw_cosine, 4),
                            "similarity_percent": round(hybrid_score * 100, 1),
                            "lexical_score": round(lex_score, 3),
                            "top_matching_file": rel_path,
                            "embedding_model": emb_model or model_name,
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
