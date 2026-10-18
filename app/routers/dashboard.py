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
    
    # Calculate verdicts distribution
    verdicts = {"SAFE": 0, "LOW": 0, "HIGH": 0, "CRITICAL": 0, "FLAGGED": 0}
    for h in history:
        v = h.get("verdict", "SAFE")
        if v in verdicts:
            verdicts[v] += 1
        else:
            verdicts["SAFE"] += 1

    # Average fusion score (overall_similarity)
    avg_score = 0
    if history:
        total = sum(h.get("overall_similarity", 0) for h in history)
        avg_score = round(total / len(history), 2)
        
    flagged_count = verdicts.get("FLAGGED", 0) + verdicts.get("HIGH", 0) + verdicts.get("CRITICAL", 0)
    
    return {
        "total_projects": db.count_projects(),
        "total_teams": db.count_teams(),
        "total_users": db.count_users(),
        "total_files": db.count_files(),
        "recent_scans": recent_scans,
        "flagged_count": flagged_count,
        "average_fusion_score": avg_score,
        "verdicts_distribution": verdicts
    }
