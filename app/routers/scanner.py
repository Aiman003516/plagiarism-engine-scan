"""Scan endpoints: uploads, ZIP, Git, SSE streaming and re-attach."""

import os
import shutil
import tempfile
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from plagiarism_engine import FileExtractor

from fastapi import APIRouter
from app.dependencies import require_role
from app.services.git_clone import _clone_git_repo
from app.services.intake import _run_analysis, _run_intake
from app.services.scan_sessions import _get_scan_session, _start_scan_session, _stream_scan_events
from app.state import get_db

router = APIRouter(tags=["scanner"])


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    scan_type: str = "project"
    target: Optional[str] = None


class GitScanRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"
    access_token: Optional[str] = None
    project_name: Optional[str] = None
    scan_type: Optional[str] = "Git Repository Scan"

@router.get("/api/plagiarism/scan-stream/{project_id}")
async def reconnect_scan_stream(
    project_id: str,
    token: str = Query(...),
    after: int = Query(0, ge=0),
):
    """Re-attach to a running (or just-finished) scan stream.

    Deliberately a GET with the capability token in the query string: this is the
    endpoint an `EventSource` reconnects to, and `EventSource` cannot POST or send
    an `Authorization` header. The token is a per-scan random secret handed to the
    client on the originating (JWT-authenticated) stream, so it grants read access
    to exactly this project's scan log and nothing else.

    `after` is the number of log lines the client already has, so the replay only
    sends what it missed (SSE `Last-Event-ID` cannot be used here because the
    client builds a fresh `EventSource` rather than letting the browser retry).
    """
    session = _get_scan_session(project_id, token)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No resumable scan stream for project '{project_id}'",
        )
    return StreamingResponse(
        _stream_scan_events(session, skip_logs=after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Upload + Scan (JSON response) ---
@router.post("/api/plagiarism/upload-scan", dependencies=[Depends(require_role())])
async def upload_and_scan(
    project_name: str = Form(...),
    scan_type: str = Form("Direct Upload Project Scan"),
    files: List[UploadFile] = File(...),
):
    extracted_files = []
    for upload_file in files:
        raw = await upload_file.read()
        filename = upload_file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        file_type = FileExtractor.categorize_file(filename)
        # Use FileExtractor for binary formats (PDF, DOCX); fall back to UTF-8 for plain text/code
        if ext in (".pdf", ".docx", ".doc"):
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                content = FileExtractor().extract_file(tmp_path) or ""
            finally:
                os.unlink(tmp_path)
        else:
            content = raw.decode("utf-8", errors="ignore")
        extracted_files.append({
            "relative_path": filename,
            "filename": Path(filename).name,
            "extension": ext,
            "file_type": file_type,
            "content": content,
        })

    # Run the CPU/IO-heavy fingerprinting + comparison work in a worker thread so the
    # async event loop is never blocked (mirrors the streaming endpoints' behaviour).
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_intake(project_name, extracted_files)
    )
    return result


# --- Upload + Scan (SSE Streaming) ---
@router.post("/api/plagiarism/upload-scan-stream", dependencies=[Depends(require_role())])
async def upload_and_scan_stream(
    project_name: str = Form(...),
    scan_type: str = Form("Direct Upload Project Scan"),
    files: List[UploadFile] = File(...),
):
    # Read files synchronously first
    extracted_files = []
    for upload_file in files:
        raw = await upload_file.read()
        filename = upload_file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        file_type = FileExtractor.categorize_file(filename)
        # Use FileExtractor for binary formats (PDF, DOCX); fall back to UTF-8 for plain text/code
        if ext in (".pdf", ".docx", ".doc"):
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                content = FileExtractor().extract_file(tmp_path) or ""
            finally:
                os.unlink(tmp_path)
        else:
            content = raw.decode("utf-8", errors="ignore")
        extracted_files.append({
            "relative_path": filename,
            "filename": Path(filename).name,
            "extension": ext,
            "file_type": file_type,
            "content": content,
        })

    # Register the resumable session BEFORE streaming so a client that navigates
    # away mid-scan can re-attach via GET /api/plagiarism/scan-stream/{project}.
    session = _start_scan_session(project_name)

    async def event_stream():
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            session.publish_log(msg)

        def run_intake():
            try:
                res = _run_intake(project_name, extracted_files, log_callback=log_callback)
                session.publish({"type": "complete", "result": res})
            except Exception as e:
                session.publish({"type": "error", "message": str(e)})

        # Hand the client its reconnect capability before any work starts.
        session.publish(session.header_event())

        # Start the background thread
        executor_task = loop.run_in_executor(None, run_intake)

        async for frame in _stream_scan_events(session):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Upload + Scan ZIP Archive (SSE Streaming) ---
@router.post("/api/plagiarism/upload-zip-stream", dependencies=[Depends(require_role())])
async def upload_zip_stream(
    project_name: str = Form(...),
    scan_type: str = Form("ZIP Archive Scan"),
    file: UploadFile = File(...),
):
    import zipfile

    tmp_dir = tempfile.mkdtemp(prefix="plagiarism_zip_")

    # Resumable session — see `_start_scan_session` and the reconnect endpoint.
    session = _start_scan_session(project_name)

    async def event_stream():
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            session.publish_log(msg)

        def run_zip_intake():
            try:
                log_callback(f"📦 Extracting ZIP archive '{file.filename}'...")
                zip_path = os.path.join(tmp_dir, "upload.zip")
                with open(zip_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                extract_dir = os.path.join(tmp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # --- Security: block Zip Slip (path traversal) before extraction ---
                    for member_name in zip_ref.namelist():
                        normalized = member_name.replace("\\", "/")
                        if os.path.isabs(normalized) or ".." in normalized.split("/"):
                            raise HTTPException(
                                status_code=400,
                                detail=f"Unsafe path in ZIP archive: {member_name}",
                            )
                    zip_ref.extractall(extract_dir)

                # --- Security: verify nothing escaped the extraction directory ---
                extract_root = os.path.abspath(extract_dir)
                for root, dirs, files in os.walk(extract_dir):
                    for entry_name in list(dirs) + list(files):
                        entry_path = os.path.abspath(os.path.join(root, entry_name))
                        if not (entry_path == extract_root or entry_path.startswith(extract_root + os.sep)):
                            shutil.rmtree(tmp_dir, ignore_errors=True)
                            raise HTTPException(
                                status_code=400,
                                detail="Unsafe path detected in ZIP archive (path traversal blocked)",
                            )

                log_callback(f"📂 Scanning extracted project directory: {project_name}...")
                extracted_files = FileExtractor.scan_project_directory(extract_dir)
                
                for f in extracted_files:
                    if "relative_path" not in f:
                        f["relative_path"] = f.get("filename", "")

                res = _run_intake(project_name, extracted_files, log_callback=log_callback)
                session.publish({"type": "complete", "result": res})
            except Exception as e:
                session.publish({"type": "error", "message": str(e)})
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # Hand the client its reconnect capability before any work starts.
        session.publish(session.header_event())

        executor_task = loop.run_in_executor(None, run_zip_intake)

        async for frame in _stream_scan_events(session):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Git Repo Scan (JSON) ---
@router.post("/api/plagiarism/git-scan", dependencies=[Depends(require_role())])
async def git_scan(payload: GitScanRequest):
    tmp_dir, git_metadata = _clone_git_repo(payload.repo_url, payload.branch or "main", payload.access_token)

    try:
        project_name = payload.project_name or Path(payload.repo_url.rstrip("/")).stem
        extracted_files = FileExtractor.scan_project_directory(tmp_dir)

        # Set relative paths
        for f in extracted_files:
            if "relative_path" not in f:
                f["relative_path"] = f.get("filename", "")

        result = _run_intake(project_name, extracted_files, git_metadata=git_metadata)
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# --- Git Repo Scan (SSE Streaming) ---
@router.post("/api/plagiarism/git-scan-stream", dependencies=[Depends(require_role())])
async def git_scan_stream(payload: GitScanRequest):
    # Resolve the project id up-front so the resumable session can be keyed by it
    # (the worker below previously derived it only after cloning).
    project_name = payload.project_name or Path(payload.repo_url.rstrip("/")).stem
    session = _start_scan_session(project_name)

    async def event_stream():
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            session.publish_log(msg)

        def run_git_intake():
            tmp_dir = None
            try:
                tmp_dir, git_metadata = _clone_git_repo(
                    payload.repo_url, payload.branch or "main", payload.access_token, log_callback=log_callback
                )

                log_callback(f"📂 Scanning project directory: {project_name}...")
                extracted_files = FileExtractor.scan_project_directory(tmp_dir)

                for f in extracted_files:
                    if "relative_path" not in f:
                        f["relative_path"] = f.get("filename", "")

                res = _run_intake(
                    project_name, extracted_files,
                    log_callback=log_callback,
                    git_metadata=git_metadata,
                )
                session.publish({"type": "complete", "result": res})
            except Exception as e:
                session.publish({"type": "error", "message": str(e)})
            finally:
                if tmp_dir:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

        # Hand the client its reconnect capability before any work starts.
        session.publish(session.header_event())

        executor_task = loop.run_in_executor(None, run_git_intake)

        async for frame in _stream_scan_events(session):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Named scan on already-indexed project ---
@router.post("/api/plagiarism/scan", dependencies=[Depends(require_role())])
async def run_scan(req: ScanRequest):
    db = get_db()
    target = req.target
    if not target:
        raise HTTPException(status_code=400, detail="No target project specified.")
        
    try:
        result = _run_analysis(target)
        result["scan_type"] = req.scan_type or "Saved Project Scan"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
