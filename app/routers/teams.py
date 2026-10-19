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


class TeamMemberAdd(BaseModel):
    enrollment_number: str


@router.get("/api/teams", dependencies=[Depends(require_role())])
async def list_teams(college_id: Optional[str] = None):
    db = get_db()
    loop = asyncio.get_running_loop()
    teams = await loop.run_in_executor(None, lambda: db.get_all_teams(college_id))
    return {"teams": teams}


@router.post("/api/teams", dependencies=[Depends(require_role())])
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


@router.put("/api/teams/{team_id}", dependencies=[Depends(require_role())])
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


@router.delete("/api/teams/{team_id}", dependencies=[Depends(require_role())])
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


@router.post("/api/teams/{team_id}/members", dependencies=[Depends(require_role())])
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


@router.delete("/api/teams/{team_id}/members/{student_id}", dependencies=[Depends(require_role())])
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
