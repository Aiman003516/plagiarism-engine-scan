"""Teams CRUD endpoints."""

import asyncio
import uuid
from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel

from fastapi import APIRouter
from app.dependencies import require_role
from app.state import get_db

router = APIRouter(tags=["teams"])


# ============================================================================
# TEAMS CRUD
# ============================================================================

class TeamCreate(BaseModel):
    name: str
    college_id: Optional[str] = None


class TeamUpdate(BaseModel):
    name: str


class ToggleSubmissionPayload(BaseModel):
    allowed: Optional[bool] = None


class TeamMemberAdd(BaseModel):
    enrollment_number: str


@router.get("/api/teams")
async def list_teams(college_id: Optional[str] = None, current_user: dict = Depends(require_role())):
    db = get_db()
    loop = asyncio.get_running_loop()
    caller_role = current_user.get("role")
    caller_id = current_user.get("user_id")

    # If student, return only their own assigned team
    if caller_role == "student":
        def _get_student_team():
            student = db.get_student_by_id(caller_id)
            if not student or not student.get("team_id"):
                return []
            team = db.get_team_by_id(student["team_id"])
            if not team:
                return []
            members = db.get_team_members(student["team_id"])
            return [{**team, "members": members}]
        teams = await loop.run_in_executor(None, _get_student_team)
        return {"teams": teams}

    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(caller_id)) or {}

    effective_college_id = college_id
    if caller_role in ("college_admin", "faculty"):
        effective_college_id = caller_record.get("college_id")
        teams = await loop.run_in_executor(None, lambda: db.get_all_teams(effective_college_id))
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        def _get_uni_teams():
            conn = db._get_connection()
            cur = conn.cursor()
            query = """
                SELECT t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                FROM teams t
                JOIN colleges c ON t.college_id = c.id
                WHERE c.university_id = %s
            """ if db.mode == "postgresql" else """
                SELECT t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                FROM teams t
                JOIN colleges c ON t.college_id = c.id
                WHERE c.university_id = ?
            """
            cur.execute(query, (caller_uni,))
            rows = cur.fetchall()
            conn.close()
            res = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    res.append(dict(r))
                else:
                    res.append({
                        "id": r[0], "name": r[1], "college_id": r[2], "created_at": r[3],
                        "submission_allowed": bool(r[4]) if len(r) > 4 else False
                    })
            return res
        teams = await loop.run_in_executor(None, _get_uni_teams)
    else:
        teams = await loop.run_in_executor(None, lambda: db.get_all_teams(effective_college_id))

    return {"teams": teams}


@router.post("/api/teams")
async def create_team(payload: TeamCreate, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    db = get_db()
    loop = asyncio.get_running_loop()
    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    effective_college_id = payload.college_id
    if caller_role in ("college_admin", "faculty"):
        caller_college = caller_record.get("college_id")
        if payload.college_id and caller_college and payload.college_id != caller_college:
            raise HTTPException(status_code=403, detail="Cannot create team outside your college.")
        effective_college_id = caller_college
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        if payload.college_id:
            def _check_col():
                conn = db._get_connection()
                cur = conn.cursor()
                q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
                cur.execute(q, (payload.college_id,))
                r = cur.fetchone()
                conn.close()
                return r[0] if r else None
            col_uni = await loop.run_in_executor(None, _check_col)
            if col_uni and caller_uni and col_uni != caller_uni:
                raise HTTPException(status_code=403, detail="Cannot create team for a college in another university.")

    team_id = str(uuid.uuid4())

    def _create():
        db.create_team(team_id, payload.name, effective_college_id)
        return db.get_team_by_id(team_id)

    team = await loop.run_in_executor(None, _create)
    return team


@router.get("/api/teams/{team_id}")
async def get_team(team_id: str, current_user: dict = Depends(require_role())):
    db = get_db()
    loop = asyncio.get_running_loop()

    caller_role = current_user.get("role")
    if caller_role == "student":
        caller_id = current_user.get("user_id")
        student_rec = await loop.run_in_executor(None, lambda: db.get_student_by_id(caller_id)) or {}
        if student_rec.get("team_id") != team_id:
            raise HTTPException(status_code=403, detail="Students can only view their own team.")

    def _get():
        team = db.get_team_by_id(team_id)
        if not team:
            return None, None
        members = db.get_team_members(team_id)
        return team, members

    team, members = await loop.run_in_executor(None, _get)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {**team, "members": members}


@router.put("/api/teams/{team_id}")
async def update_team(team_id: str, payload: TeamUpdate, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _update():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return None, "NOT_FOUND"

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        team_college = existing.get("college_id")
        if caller_role in ("college_admin", "faculty"):
            caller_college = caller_record.get("college_id")
            if team_college and caller_college and team_college != caller_college:
                return None, "FORBIDDEN"
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            conn = db._get_connection()
            cur = conn.cursor()
            q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
            cur.execute(q, (team_college,))
            r = cur.fetchone()
            conn.close()
            if not r or r[0] != caller_uni:
                return None, "FORBIDDEN"

        db.update_team(team_id, name=payload.name)
        return db.get_team_by_id(team_id), "OK"

    updated, status = await loop.run_in_executor(None, _update)
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Insufficient permissions to modify a team from another college.")
    return updated


@router.post("/api/teams/{team_id}/toggle-submission")
async def toggle_team_submission(team_id: str, payload: ToggleSubmissionPayload = None, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    """
    Allow faculty supervisors / admins to grant or revoke a one-time proposal
    submission token for a student team.
    """
    db = get_db()
    loop = asyncio.get_running_loop()

    def _toggle():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return None, "NOT_FOUND"

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        team_college = existing.get("college_id")
        if caller_role in ("college_admin", "faculty"):
            caller_college = caller_record.get("college_id")
            if team_college and caller_college and team_college != caller_college:
                return None, "FORBIDDEN"
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            conn = db._get_connection()
            cur = conn.cursor()
            q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
            cur.execute(q, (team_college,))
            r = cur.fetchone()
            conn.close()
            if not r or r[0] != caller_uni:
                return None, "FORBIDDEN"

        current_state = bool(existing.get("submission_allowed", False))
        new_state = (not current_state) if (payload is None or payload.allowed is None) else bool(payload.allowed)
        db.update_team(team_id, submission_allowed=new_state)
        return db.get_team_by_id(team_id), "OK"

    updated, status = await loop.run_in_executor(None, _toggle)
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Insufficient permissions to toggle submission for a team outside your institution.")
    return updated


@router.delete("/api/teams/{team_id}")
async def delete_team(team_id: str, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin"))):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _delete():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return "NOT_FOUND"

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        team_college = existing.get("college_id")
        if caller_role == "college_admin":
            caller_college = caller_record.get("college_id")
            if team_college and caller_college and team_college != caller_college:
                return "FORBIDDEN"
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            conn = db._get_connection()
            cur = conn.cursor()
            q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
            cur.execute(q, (team_college,))
            r = cur.fetchone()
            conn.close()
            if not r or r[0] != caller_uni:
                return "FORBIDDEN"

        db.delete_team(team_id)
        return "OK"

    status = await loop.run_in_executor(None, _delete)
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Insufficient permissions to delete a team from another institution.")
    return {"detail": "Team deleted"}


@router.post("/api/teams/{team_id}/members")
async def add_team_member_endpoint(team_id: str, payload: TeamMemberAdd, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _add():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return "TEAM_NOT_FOUND", None

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        team_college = existing.get("college_id")
        if caller_role in ("college_admin", "faculty"):
            caller_college = caller_record.get("college_id")
            if team_college and caller_college and team_college != caller_college:
                return "FORBIDDEN", None
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            conn = db._get_connection()
            cur = conn.cursor()
            q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
            cur.execute(q, (team_college,))
            r = cur.fetchone()
            conn.close()
            if not r or r[0] != caller_uni:
                return "FORBIDDEN", None

        student = db.get_student_by_enrollment_number(payload.enrollment_number)
        if not student:
            return "STUDENT_NOT_FOUND", None

        if caller_role in ("college_admin", "faculty"):
            if student.get("college_id") and team_college and student.get("college_id") != team_college:
                return "CROSS_COLLEGE_STUDENT", None
        elif caller_role == "university_admin":
            if student.get("university_id") and caller_uni and student.get("university_id") != caller_uni:
                return "CROSS_COLLEGE_STUDENT", None

        db.add_team_member(team_id, student["id"])
        return "OK", db.get_team_members(team_id)

    status, members = await loop.run_in_executor(None, _add)
    if status == "TEAM_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Insufficient permissions to add members to a team from another institution.")
    if status == "CROSS_COLLEGE_STUDENT":
        raise HTTPException(status_code=400, detail="Cannot assign a student from another college to this team.")
    if status == "STUDENT_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Student not found")
    return {"members": members}


@router.delete("/api/teams/{team_id}/members/{student_id}")
async def remove_team_member_endpoint(team_id: str, student_id: str, current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _remove():
        team = db.get_team_by_id(team_id)
        if not team:
            return "TEAM_NOT_FOUND"

        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        team_college = team.get("college_id")
        if caller_role in ("college_admin", "faculty"):
            caller_college = caller_record.get("college_id")
            if team_college and caller_college and team_college != caller_college:
                return "FORBIDDEN"
        elif caller_role == "university_admin":
            caller_uni = caller_record.get("university_id")
            conn = db._get_connection()
            cur = conn.cursor()
            q = "SELECT university_id FROM colleges WHERE id = %s" if db.mode == "postgresql" else "SELECT university_id FROM colleges WHERE id = ?"
            cur.execute(q, (team_college,))
            r = cur.fetchone()
            conn.close()
            if not r or r[0] != caller_uni:
                return "FORBIDDEN"

        members = db.get_team_members(team_id)
        if not any(m["id"] == student_id for m in members):
            return "NOT_MEMBER"
        db.remove_team_member(student_id)
        return "OK"

    status = await loop.run_in_executor(None, _remove)
    if status == "TEAM_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "FORBIDDEN":
        raise HTTPException(status_code=403, detail="Insufficient permissions to modify a team from another institution.")
    if status == "NOT_MEMBER":
        raise HTTPException(status_code=404, detail="Student is not a member of this team")
    return {"detail": "Student removed from team"}



@router.get("/api/teams/students/search")
async def search_students_for_teams(q: str = "", current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))):
    """Search students by name or enrollment number for team assignment."""
    db = get_db()
    loop = asyncio.get_running_loop()

    def _search():
        conn = db._get_connection()
        cur = conn.cursor()
        query = f"%{q.strip().lower()}%"
        caller_role = current_user.get("role")
        caller_record = db.get_user_by_id(current_user["user_id"]) or {}
        caller_college = caller_record.get("college_id")
        caller_uni = caller_record.get("university_id")

        conds = ["(LOWER(s.name) LIKE %s OR LOWER(s.enrollment_number) LIKE %s)"] if db.mode == "postgresql" else ["(LOWER(s.name) LIKE ? OR LOWER(s.enrollment_number) LIKE ?)"]
        params = [query, query]

        if caller_role in ("college_admin", "faculty") and caller_college:
            conds.append("s.college_id = %s" if db.mode == "postgresql" else "s.college_id = ?")
            params.append(caller_college)
        elif caller_role == "university_admin" and caller_uni:
            conds.append("s.university_id = %s" if db.mode == "postgresql" else "s.university_id = ?")
            params.append(caller_uni)

        where_clause = " AND ".join(conds)
        sql = f"""
            SELECT s.id, s.enrollment_number, s.name, s.college_id, s.team_id, t.name as team_name
            FROM students s LEFT JOIN teams t ON s.team_id = t.id
            WHERE {where_clause}
            ORDER BY s.name ASC LIMIT 20;
        """
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        conn.close()
        results = []
        for r in rows:
            if hasattr(r, "keys"):
                results.append(dict(r))
            else:
                results.append({
                    "id": r[0],
                    "enrollment_number": r[1],
                    "name": r[2],
                    "college_id": r[3],
                    "team_id": r[4],
                    "team_name": r[5] if len(r) > 5 else None,
                })
        return results

    students = await loop.run_in_executor(None, _search)
    return {"students": students}
