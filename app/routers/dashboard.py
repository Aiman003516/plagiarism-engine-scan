"""System health and dashboard statistics endpoints."""

import asyncio
import time

from app import state

from fastapi import APIRouter, Depends
from app.dependencies import require_role
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

@router.get("/api/dashboard/stats", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def dashboard_stats():
    db = get_db()
    loop = asyncio.get_running_loop()

    def _compute():
        history = _load_history()
        recent_scans = history[::-1][:10] if history else []
        
        # Calculate verdicts distribution across historical scans
        verdicts = {"SAFE": 0, "LOW": 0, "HIGH": 0, "CRITICAL": 0, "FLAGGED": 0}
        for h in history:
            v = h.get("verdict", "SAFE")
            if v in verdicts:
                verdicts[v] += 1
            else:
                verdicts["SAFE"] += 1

        # Average fusion score (overall_similarity) across completed scans
        avg_score = 0.0
        if history:
            total = sum(h.get("overall_similarity", 0) for h in history)
            avg_score = round(total / len(history), 2)
            
        # Distinct project health calculation using fast project names query
        project_names = db.get_all_project_names()
        latest_by_project = {}
        for h in history:
            pname = h.get("project_name")
            if pname:
                latest_by_project[pname] = h.get("verdict", "SAFE")

        safe_projects = 0
        flagged_projects = 0
        for pname in project_names:
            v = latest_by_project.get(pname, "SAFE")
            if v in ("HIGH", "CRITICAL", "FLAGGED"):
                flagged_projects += 1
            else:
                safe_projects += 1

        return {
            "total_projects": len(project_names),
            "total_teams": db.count_teams(),
            "total_users": db.count_users(),
            "total_files": db.count_files(),
            "recent_scans": recent_scans,
            "flagged_count": flagged_projects,
            "safe_projects": safe_projects,
            "total_scans": len(history),
            "average_fusion_score": avg_score,
            "verdicts_distribution": verdicts,
        }

    stats = await loop.run_in_executor(None, _compute)
    return stats
