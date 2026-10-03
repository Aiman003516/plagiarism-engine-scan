"""Teams CRUD endpoints."""

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
    return {"teams": db.get_all_teams(college_id)}


@router.post("/api/teams", dependencies=[Depends(require_role())])
async def create_team(payload: TeamCreate):
    db = get_db()
    team_id = str(uuid.uuid4())
    db.create_team(team_id, payload.name, payload.college_id)
    team = db.get_team_by_id(team_id)
    return team


@router.get("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def get_team(team_id: str):
    db = get_db()
    team = db.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = db.get_team_members(team_id)
    return {**team, "members": members}


@router.put("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def update_team(team_id: str, payload: TeamUpdate):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.update_team(team_id, name=payload.name)
    return db.get_team_by_id(team_id)


@router.delete("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def delete_team(team_id: str):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete_team(team_id)
    return {"detail": "Team deleted"}


@router.post("/api/teams/{team_id}/members", dependencies=[Depends(require_role())])
async def add_team_member_endpoint(team_id: str, payload: TeamMemberAdd):
    db = get_db()
    team = db.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    student = db.get_student_by_enrollment_number(payload.enrollment_number)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    db.add_team_member(team_id, student["id"])
    return {"members": db.get_team_members(team_id)}


@router.delete("/api/teams/{team_id}/members/{student_id}", dependencies=[Depends(require_role())])
async def remove_team_member_endpoint(team_id: str, student_id: str):
    db = get_db()
    team = db.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = db.get_team_members(team_id)
    if not any(m["id"] == student_id for m in members):
        raise HTTPException(status_code=404, detail="Student is not a member of this team")
    db.remove_team_member(student_id)
    return {"detail": "Student removed from team"}
