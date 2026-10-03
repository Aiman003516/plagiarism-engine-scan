"""System settings endpoints."""

from typing import Dict, Any
from fastapi import Depends


from fastapi import APIRouter
from app.dependencies import require_role
from app.state import get_db

router = APIRouter(tags=["settings"])


@router.get("/api/settings")
async def get_settings():
    db = get_db()
    return db.get_all_settings()


@router.put("/api/settings", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def update_settings(payload: Dict[str, Any]):
    db = get_db()
    db.update_settings(payload)
    return db.get_all_settings()
