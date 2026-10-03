"""System health and dashboard statistics endpoints."""

import time


from app import state

from fastapi import APIRouter
from app.state import _load_history, get_db

router = APIRouter(tags=["dashboard"])


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/api/system/health")
async def health_check():
    return {
        "status": "healthy",
        "biometrics": "not_available",
        "plagiarism": "operational",
        "models_ready": state._models_ready,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

@router.get("/api/dashboard/stats")
async def dashboard_stats():
    db = get_db()
    history = _load_history()
    recent_scans = history[::-1][:10] if history else []
    flagged_count = sum(1 for h in history if h.get("verdict") == "FLAGGED")
    return {
        "total_projects": db.count_projects(),
        "total_teams": db.count_teams(),
        "total_users": db.count_users(),
        "total_files": db.count_files(),
        "recent_scans": recent_scans,
        "flagged_count": flagged_count,
    }
