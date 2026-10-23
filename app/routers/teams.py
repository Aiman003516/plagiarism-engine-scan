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

    # If student, return only their own assigned team
    if current_user.get("role") == "student":
        def _get_student_team():
            student = db.get_student_by_id(current_user["user_id"])
            if not student or not student.get("team_id"):
                return []
            team = db.get_team_by_id(student["team_id"])
            if not team:
                return []
            members = db.get_team_members(student["team_id"])
            return [{**team, "members": members}]
        teams = await loop.run_in_executor(None, _get_student_team)
        return {"teams": teams}

    teams = await loop.run_in_executor(None, lambda: db.get_all_teams(college_id))
    return {"teams": teams}


@router.post("/api/teams", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def create_team(payload: TeamCreate):
    db = get_db()
    loop = asyncio.get_running_loop()
    team_id = str(uuid.uuid4())

    def _create():
        db.create_team(team_id, payload.name, payload.college_id)
        return db.get_team_by_id(team_id)

    team = await loop.run_in_executor(None, _create)
    return team


@router.get("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def get_team(team_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()

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


@router.put("/api/teams/{team_id}", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def update_team(team_id: str, payload: TeamUpdate):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _update():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return None
        db.update_team(team_id, name=payload.name)
        return db.get_team_by_id(team_id)

    updated = await loop.run_in_executor(None, _update)
    if not updated:
        raise HTTPException(status_code=404, detail="Team not found")
    return updated


@router.post("/api/teams/{team_id}/toggle-submission", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def toggle_team_submission(team_id: str, payload: ToggleSubmissionPayload = None):
    """
    Allow faculty supervisors / admins to grant or revoke a one-time proposal
    submission token for a student team.
    """
    db = get_db()
    loop = asyncio.get_running_loop()

    def _toggle():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return None
        current_state = bool(existing.get("submission_allowed", False))
        new_state = (not current_state) if (payload is None or payload.allowed is None) else bool(payload.allowed)
        db.update_team(team_id, submission_allowed=new_state)
        return db.get_team_by_id(team_id)

    updated = await loop.run_in_executor(None, _toggle)
    if not updated:
        raise HTTPException(status_code=404, detail="Team not found")
    return updated


@router.delete("/api/teams/{team_id}", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin"))])
async def delete_team(team_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _delete():
        existing = db.get_team_by_id(team_id)
        if not existing:
            return False
        db.delete_team(team_id)
        return True

    found = await loop.run_in_executor(None, _delete)
    if not found:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"detail": "Team deleted"}


@router.post("/api/teams/{team_id}/members", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def add_team_member_endpoint(team_id: str, payload: TeamMemberAdd):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _add():
        team = db.get_team_by_id(team_id)
        if not team:
            return "TEAM_NOT_FOUND", None
        student = db.get_student_by_enrollment_number(payload.enrollment_number)
        if not student:
            return "STUDENT_NOT_FOUND", None
        db.add_team_member(team_id, student["id"])
        return "OK", db.get_team_members(team_id)

    status, members = await loop.run_in_executor(None, _add)
    if status == "TEAM_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "STUDENT_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Student not found")
    return {"members": members}


@router.delete("/api/teams/{team_id}/members/{student_id}", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def remove_team_member_endpoint(team_id: str, student_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _remove():
        team = db.get_team_by_id(team_id)
        if not team:
            return "TEAM_NOT_FOUND"
        members = db.get_team_members(team_id)
        if not any(m["id"] == student_id for m in members):
            return "NOT_MEMBER"
        db.remove_team_member(student_id)
        return "OK"

    status = await loop.run_in_executor(None, _remove)
    if status == "TEAM_NOT_FOUND":
        raise HTTPException(status_code=404, detail="Team not found")
    if status == "NOT_MEMBER":
        raise HTTPException(status_code=404, detail="Student is not a member of this team")
    return {"detail": "Student removed from team"}



@router.get("/api/teams/students/search", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def search_students_for_teams(q: str = ""):
    """Search students by name or enrollment number for team assignment."""
    db = get_db()
    loop = asyncio.get_running_loop()

    def _search():
        conn = db._get_connection()
        cur = conn.cursor()
        query = f"%{q.strip().lower()}%"
        if db.mode == "postgresql":
            cur.execute(
                "SELECT s.id, s.enrollment_number, s.name, s.college_id, s.team_id, t.name as team_name "
                "FROM students s LEFT JOIN teams t ON s.team_id = t.id "
                "WHERE LOWER(s.name) LIKE %s OR LOWER(s.enrollment_number) LIKE %s "
                "ORDER BY s.name ASC LIMIT 20;",
                (query, query),
            )
        else:
            cur.execute(
                "SELECT s.id, s.enrollment_number, s.name, s.college_id, s.team_id, t.name as team_name "
                "FROM students s LEFT JOIN teams t ON s.team_id = t.id "
                "WHERE LOWER(s.name) LIKE ? OR LOWER(s.enrollment_number) LIKE ? "
                "ORDER BY s.name ASC LIMIT 20;",
                (query, query),
            )
        rows = cur.fetchall()
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
