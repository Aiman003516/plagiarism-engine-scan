"""Scan history endpoints (list / detail / delete)."""

from typing import Dict, Any, Optional
from fastapi import HTTPException, Depends


from fastapi import APIRouter
from app.dependencies import require_role
from app.state import _load_history, _save_history

router = APIRouter(tags=["history"])


# --- Scan history (list / detail / delete) ---
def _history_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Project a stored scan report down to the keys the frontend history list uses."""
    return {
        "id": entry.get("id", ""),
        "project_name": entry.get("project_name", ""),
        "scan_type": entry.get("scan_type", ""),
        "overall_similarity": entry.get("overall_similarity", 0),
        "code_similarity": entry.get("code_similarity", 0),
        "text_similarity": entry.get("text_similarity", 0),
        "verdict": entry.get("verdict", "SAFE"),
        "total_files": entry.get("total_files", 0),
        "total_loc": entry.get("total_loc", 0),
        "timestamp": entry.get("timestamp", ""),
    }


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


@router.get("/api/plagiarism/history", dependencies=[Depends(require_role())])
async def get_scan_history():
    """Return every stored scan report as a lightweight summary list."""
    history = _load_history()
    return {"reports": [_history_summary(entry) for entry in history]}


@router.get("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role())])
async def get_scan_history_detail(report_id: str):
    """Return one full scan report (comparisons, stats, languages, git metadata)."""
    entry = _find_history_report(report_id)
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


@router.delete("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role())])
async def delete_scan_history_report(report_id: str):
    """Delete a single stored scan report."""
    history = _load_history()
    remaining = [entry for entry in history if entry.get("id") != report_id]
    if len(remaining) == len(history):
        raise HTTPException(status_code=404, detail=f"Scan report '{report_id}' not found")
    _save_history(remaining)
    return {"status": "success", "message": f"Scan report '{report_id}' deleted"}
