"""Scan history endpoints (list / detail / delete)."""

import asyncio
from typing import Dict, Any, Optional
from fastapi import HTTPException, Depends

from fastapi import APIRouter
from app.dependencies import require_role
from app.state import _load_history, _save_history, _load_history_summaries

router = APIRouter(tags=["history"])


# --- Scan history (list / detail / delete) ---
def _find_history_report(report_id: str) -> Optional[Dict[str, Any]]:
    """Look up a stored report by scan id, falling back to a project's newest scan.

    The frontend "Inspect" button navigates with `?project=<project_name || id>`,
    so the lookup key may be a project name instead of a scan id.
    """
    history = _load_history()
    for entry in history:
        if entry.get("id") == report_id:
            return entry
    # New scans are prepended, so the first match is the most recent one.
    for entry in history:
        if entry.get("project_name") == report_id:
            return entry
    return None


@router.get("/api/plagiarism/history", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def get_scan_history():
    """Return every stored scan report as a lightweight summary list with in-memory caching."""
    loop = asyncio.get_running_loop()
    reports = await loop.run_in_executor(None, _load_history_summaries)
    return {"reports": reports}


@router.get("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role("ministry_admin", "university_admin", "college_admin", "faculty"))])
async def get_scan_history_detail(report_id: str):
    """Return one full scan report (comparisons, stats, languages, git metadata)."""
    loop = asyncio.get_running_loop()
    entry = await loop.run_in_executor(None, lambda: _find_history_report(report_id))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Scan report '{report_id}' not found")

    report = dict(entry)
    # Guarantee the keys the report page reads so it never crashes on old records.
    report.setdefault("status", "completed")
    report.setdefault("id", report_id)
    report.setdefault("project_name", "")
    report.setdefault("scan_type", "")
    report.setdefault("overall_similarity", 0)
    report.setdefault("code_similarity", 0)
    report.setdefault("text_similarity", 0)
    report.setdefault("verdict", "SAFE")
    report.setdefault("threshold", 65)
    report.setdefault("comparisons", [])
    report.setdefault("code_files_count", 0)
    report.setdefault("text_files_count", 0)
    report.setdefault("total_files", 0)
    report.setdefault("total_loc", 0)
    report.setdefault("languages_detected", [])
    report.setdefault("timestamp", "")
    return report


@router.delete("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role("ministry_admin"))])
async def delete_scan_history_report(report_id: str):
    """Delete a single stored scan report."""
    loop = asyncio.get_running_loop()

    def _delete():
        history = _load_history()
        remaining = [entry for entry in history if entry.get("id") != report_id]
        if len(remaining) == len(history):
            return False
        _save_history(remaining)
        return True

    found = await loop.run_in_executor(None, _delete)
    if not found:
        raise HTTPException(status_code=404, detail=f"Scan report '{report_id}' not found")
    return {"status": "success", "message": f"Scan report '{report_id}' deleted"}
