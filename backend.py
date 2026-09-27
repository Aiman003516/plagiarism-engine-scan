"""
Standalone FastAPI Backend for the Plagiarism Detection Engine.

Provides all REST API endpoints that the React frontend consumes:
  - Project listing & existence checks
  - File upload + scan (JSON & SSE streaming)
  - Git repository clone + scan (JSON & SSE streaming)
  - Scan history (CRUD)
  - System health check

Run:
    uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import re
import sys
import time
import uuid
import json
import shutil
import tempfile
import subprocess
import asyncio
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

# Increase Starlette's max_files limit to allow uploading massive project folders
import starlette.formparsers
starlette.formparsers.MultiPartParser.max_files = 100000
starlette.formparsers.MultiPartParser.max_fields = 100000

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt, JWTError

# ---------------------------------------------------------------------------
# Ensure local plagiarism_engine package is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from plagiarism_engine import (
    FileExtractor,
    CodePlagiarismDetector,
    TextPlagiarismDetector,
    VectorStore,
    SystemDBStore,
)

# ---------------------------------------------------------------------------
# Lazy model preloading
# ---------------------------------------------------------------------------
import threading

_models_ready = False
_model_lock = threading.Lock()


def _preload_models():
    """Background preload of ML models so first scan is fast."""
    global _models_ready
    try:
        from plagiarism_engine.vector_store import model_pool
        model_pool.get_model("code")
        model_pool.get_model("bge_m3")
        model_pool.get_model("minilm")
        _models_ready = True
    except Exception as e:
        print(f"Failed to preload models: {e}")


@asynccontextmanager
async def lifespan(application: FastAPI):
    thread = threading.Thread(target=_preload_models, daemon=True)
    thread.start()
    yield


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Plagiarism Detection Engine API",
    description="Isolated standalone plagiarism scanning backend.",
    lifespan=lifespan,
)

# A wildcard origin cannot be combined with `allow_credentials=True` on
# credentialed requests, so the allowed origins are listed explicitly.
# The Vite dev server runs on port 3000 (frontend/package.json: "vite --port=3000").
# Override with PLAGIARISM_CORS_ORIGINS="http://host-a,http://host-b" when needed.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "PLAGIARISM_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Singletons (cached)
# ---------------------------------------------------------------------------
_db: Optional[SystemDBStore] = None
_vstore: Optional[VectorStore] = None

DATA_DIR = Path(os.environ.get("PLAGIARISM_DATA_DIR", str(Path(__file__).parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Deep AI scan model cache (loaded once per server lifetime)
_MODELS_DIR = os.environ.get("MODELS_DIR", r"D:\AI engine\models")
_deep_scan_models: Dict[str, Any] = {}
_deep_scan_model_lock = threading.Lock()


def _get_deep_scan_model(model_name: str):
    """Load (and cache) a SentenceTransformer model by name. Thread-safe."""
    from sentence_transformers import SentenceTransformer

    model_key = model_name
    if model_key in _deep_scan_models:
        return _deep_scan_models[model_key]

    with _deep_scan_model_lock:
        # Double-check under lock in case another thread raced us.
        if model_key in _deep_scan_models:
            return _deep_scan_models[model_key]

        model_path = os.path.join(_MODELS_DIR, model_name)
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model path not found: {model_path}")

        model = SentenceTransformer(model_path)
        # UniXcoder / BGE-M3 positional embeddings are bounded; cap the
        # token window to avoid "index out of bounds" on long files.
        try:
            model.max_seq_length = 512
        except Exception:
            pass
        _deep_scan_models[model_key] = model
        return model


def get_db() -> SystemDBStore:
    global _db
    if _db is None:
        _db = SystemDBStore(sqlite_db_path=str(DATA_DIR / "system_db.sqlite"))
    return _db


def get_vstore() -> VectorStore:
    global _vstore
    if _vstore is None:
        _vstore = VectorStore(
            index_dir=str(DATA_DIR / "faiss_index"),
            mapping_path=str(DATA_DIR / "faiss_mapping.json"),
        )
    return _vstore


# ---------------------------------------------------------------------------
# In-memory scan history (persisted to a JSON file for simplicity)
# ---------------------------------------------------------------------------
HISTORY_FILE = DATA_DIR / "scan_history.json"


def _load_history() -> List[Dict[str, Any]]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            backup_path = HISTORY_FILE.with_suffix(f".corrupt.{int(datetime.now().timestamp())}.json")
            HISTORY_FILE.rename(backup_path)
            print(f"Failed to load history, backed up corrupted file to {backup_path}: {e}")
            return []
    return []


def _save_history(history: List[Dict[str, Any]]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Utility: Run a full plagiarism scan on extracted files
# ---------------------------------------------------------------------------
def _run_intake(
    project_name: str,
    project_files: List[Dict[str, Any]],
    log_callback=None,
    git_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute code + text intake (extraction, Winnowing, and DB indexing)."""
    db = get_db()
    # PERF: the FAISS vector store is no longer touched during intake.
    # Deep semantic indexing (CodeBERT / BGE-M3 embeddings) is deferred to
    # Deep Scan mode, so the singleton is not even instantiated here.
    # Re-enable together with the `index_project_files()` block below.
    # vstore = get_vstore()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    from plagiarism_engine.winnowing import WinnowingEngine
    winnow = WinnowingEngine()

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log(f"[PHASE 1/3] 📂 Extracted {len(project_files)} files from '{project_name}'")

    code_files = [f for f in project_files if f.get("file_type") == "code"]
    text_files = [f for f in project_files if f.get("file_type") == "text"]

    log(f"   → {len(code_files)} code files, {len(text_files)} text files")

    total_loc = 0
    languages: set = set()
    for f in project_files:
        content = f.get("content", "")
        total_loc += len([l for l in content.splitlines() if l.strip()])
        ext = f.get("extension", "")
        if ext:
            languages.add(ext.lstrip("."))

    log("[PHASE 2/3] 💾 Indexing project files into database (with Zlib compression)...")
    db.save_project(project_id=project_name, project_name=project_name, files=project_files)

    # ------------------------------------------------------------------
    # PERF: Deep Semantic Indexing DECOUPLED from the upload stream.
    #
    # `VectorStore.index_project_files()` encoded every file with CodeBERT
    # (code) / BGE-M3 (text) and pushed the vectors into FAISS
    # (`add_with_ids` + `faiss.write_index`). That dominated upload latency
    # (minutes on large projects) while providing no value to the immediate
    # Winnowing result, so it is now DEFERRED to Deep Scan mode.
    #
    # The vector store itself is untouched and stays available for the
    # deferred Deep Scan indexer — to restore eager indexing, uncomment the
    # `vstore = get_vstore()` line at the top of this function plus the
    # block below.
    # ------------------------------------------------------------------
    log("[PHASE 2/3] Skipping Deep Semantic Indexing (Deferred to Deep Scan mode)...")
    # try:
    #     vstore.index_project_files(
    #         project_files=project_files,
    #         project_id=project_name,
    #         log_callback=log,
    #     )
    # except Exception as e:
    #     log(f"   ⚠️ Vector indexing warning: {e}")

    log("[PHASE 3/3] 🔮 Computing Winnowing fingerprints...")
    t0 = time.time()
    total_fingerprints = 0
    
    file_fingerprints = {}
    for idx, f in enumerate(project_files):
        content = f.get("content", "")
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        
        if not content.strip():
            continue
            
        if ftype == "code":
            fps = winnow.compute_code_fingerprints(content, rel_path)
        elif ftype == "text":
            fps = winnow.compute_text_fingerprints(content)
        else:
            continue
            
        file_fingerprints[rel_path] = fps
        total_fingerprints += len(fps)
        if idx > 0 and idx % 100 == 0:
            log(f"   → Computed fingerprints for {idx}/{len(project_files)} files...")
            
    t1 = time.time()
    log(f"   ✅ {total_fingerprints} fingerprints computed in {round(t1-t0, 1)}s")

    log("💾 Storing new fingerprints to database index (batch mode)...")
    batch = []
    for f in project_files:
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if fps:
            batch.append((rel_path, ftype, fps))
    db.store_fingerprints_batch(project_name, batch)
    log(f"✅ Intake complete for project: {project_name}")

    result = {
        "status": "completed",
        "project_name": project_name,
        "code_files_count": len(code_files),
        "text_files_count": len(text_files),
        "total_files": len(project_files),
        "total_loc": total_loc,
        "languages_detected": sorted(languages),
        "timestamp": timestamp,
    }

    if git_metadata:
        result["git_metadata"] = git_metadata

    return result


def _run_analysis(
    project_name: str,
    log_callback=None,
) -> Dict[str, Any]:
    """Run plagiarism scan against existing corpus for a saved project."""
    db = get_db()
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    def log(msg: str):
        if log_callback:
            log_callback(msg)

    log(f"[PHASE 1/3] 📂 Loading project '{project_name}' from database...")
    project_files = db.get_project_files(project_name)
    if not project_files:
        raise ValueError(f"Project '{project_name}' not found in database.")
        
    code_files = [f for f in project_files if f.get("file_type") == "code"]
    text_files = [f for f in project_files if f.get("file_type") == "text"]
    
    total_loc = 0
    languages: set = set()
    for f in project_files:
        content = f.get("content", "")
        total_loc += len([l for l in content.splitlines() if l.strip()])
        ext = Path(f.get("relative_path", "")).suffix.lower()
        if ext:
            languages.add(ext.lstrip("."))

    log("[PHASE 2/3] 🔍 Querying fingerprint index for candidates...")
    
    # Fetch fingerprints for this project
    file_fingerprints = db.get_project_fingerprints(project_name)
    
    all_comparisons: List[Dict[str, Any]] = []
    max_code_sim = 0.0
    max_text_sim = 0.0

    total_candidates = 0

    for f in project_files:
        rel_path = f.get("relative_path", "")
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        
        if not fps:
            continue
            
        fp_hashes = [h for h, p in fps]
        total_fps = len(fp_hashes)
        
        candidates = db.query_candidates(fp_hashes, ftype, project_name)
        
        # Filter candidates: must share at least 5 fingerprints or 10%
        valid_candidates = {key: count for key, count in candidates.items() if count >= 5 or (count / total_fps) > 0.1}
        total_candidates += len(valid_candidates)
        
        for key, count in valid_candidates.items():
            other_pid, other_path = key.split("::", 1)
            
            target_fps = db.get_file_fingerprint_count(other_pid, other_path)
            if not target_fps:
                continue
                
            # Overlap coefficient: shared / min(source, target) allows detecting small files pasted inside large ones
            sim_val = min(count / min(total_fps, target_fps), 1.0)
            
            if ftype == "code":
                if sim_val >= 0.25:  # Lowered threshold to see results
                    max_code_sim = max(max_code_sim, sim_val)
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "type": "Code",
                        "status": "FLAGGED" if sim_val >= 0.65 else "Moderate"
                    })
            elif ftype == "text":
                if sim_val >= 0.20:
                    max_text_sim = max(max_text_sim, sim_val)
                    all_comparisons.append({
                        "project": other_pid,
                        "file1": rel_path,
                        "file2": other_path,
                        "similarity": f"{round(sim_val * 100, 2)}%",
                        "type": "Text",
                        "status": "FLAGGED" if sim_val >= 0.5 else "Moderate"
                    })

    log(f"   ✅ Scan complete: {len(all_comparisons)} matches from {total_candidates} candidates.")

    # Phase 3: ML-enhanced verification on top Winnowing matches
    log("[PHASE 3/3] 🤖 Running ML verification on top matches...")
    code_detector = CodePlagiarismDetector()
    text_detector = TextPlagiarismDetector()

    for cmp in all_comparisons[:20]:  # Only verify top 20 to save time
        try:
            other_pid = cmp["project"]
            source_content = ""
            target_content = ""

            # Get source file content
            for f in project_files:
                if f.get("relative_path", "") == cmp.get("file1", ""):
                    source_content = f.get("content", "")
                    break

            # Get target file content from DB.
            # NOTE: get_files_by_paths() excludes the project_id passed to it, so we pass the
            # *source* project and then select the row belonging to the matched (other) project.
            target_files = db.get_files_by_paths(project_name, [cmp.get("file2", "")])
            matched = [
                t for t in target_files
                if t.get("project_id") == other_pid and t.get("relative_path") == cmp.get("file2", "")
            ]
            if matched:
                target_content = matched[0].get("content", "")
            elif target_files:
                target_content = target_files[0].get("content", "")

            if source_content and target_content:
                if cmp.get("type") == "Code":
                    # compare_code() reports its hybrid composite score under the "similarity" key.
                    ml_result = code_detector.compare_code(source_content, target_content)
                    cmp["ml_similarity"] = f"{round(ml_result.get('similarity', 0) * 100, 2)}%"
                else:
                    ml_result = text_detector.compare_pair(source_content, target_content)
                    cmp["ml_similarity"] = f"{round(ml_result.get('similarity', 0) * 100, 2)}%"
        except Exception as e:
            cmp["ml_similarity"] = "N/A"

    overall = round(max(max_code_sim, max_text_sim) * 100, 2)
    verdict = "FLAGGED" if overall >= 65 else "SAFE"

    log(f"✅ Full run complete. Overall similarity: {overall}% — Verdict: {verdict}")

    result = {
        "status": "completed",
        "id": scan_id,
        "project_name": project_name,
        "overall_similarity": overall,
        "code_similarity": round(max_code_sim * 100, 2),
        "text_similarity": round(max_text_sim * 100, 2),
        "verdict": verdict,
        "threshold": 65,
        "comparisons": all_comparisons,
        "code_files_count": len(code_files),
        "text_files_count": len(text_files),
        "total_files": len(project_files),
        "total_loc": total_loc,
        "languages_detected": sorted(languages),
        "timestamp": timestamp,
    }

    # Persist to history
    history = _load_history()
    history.insert(0, result)
    _save_history(history)

    return result


# ---------------------------------------------------------------------------
# Utility: Clone a git repository
# ---------------------------------------------------------------------------
def _clone_git_repo(repo_url: str, branch: str = "main", access_token: Optional[str] = None, log_callback=None) -> tuple:
    """Clone a git repo to a temp dir and return (temp_dir_path, git_metadata_dict)."""

    # --- Security: validate inputs to prevent git option / command injection ---
    if not isinstance(repo_url, str) or not repo_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid repository URL or branch name")
    if not branch or not re.match(r"^[a-zA-Z0-9._\-/]+$", branch):
        raise HTTPException(status_code=400, detail="Invalid repository URL or branch name")

    def log(msg):
        if log_callback:
            log_callback(msg)

    tmp_dir = tempfile.mkdtemp(prefix="plagiarism_git_")

    # Inject token into URL if provided (supports GitHub, GitLab, Bitbucket)
    clone_url = repo_url
    if access_token and clone_url.startswith("https://"):
        domain_part = clone_url[8:]
        clone_url = f"https://oauth2:{access_token}@{domain_part}"

    log(f"🔗 Cloning repository: {repo_url} (branch: {branch})...")

    # Skip Git LFS (Large File Storage) objects to speed up clones
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, "--", clone_url, tmp_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Git clone failed: {e.stderr}")
    except FileNotFoundError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Git is not installed on the server.")

    log("✅ Repository cloned successfully.")

    # Extract git metadata
    git_metadata = {"repo_url": repo_url, "branch": branch, "commits": [], "contributors": [], "commit_sha": ""}
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-10", "--format=%H|||%an|||%ai|||%s"],
            cwd=tmp_dir, capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split("|||")
            if len(parts) == 4:
                git_metadata["commits"].append({
                    "sha": parts[0][:7], "author": parts[1], "date": parts[2], "message": parts[3]
                })
        if git_metadata["commits"]:
            git_metadata["commit_sha"] = git_metadata["commits"][0]["sha"]
    except Exception as e:
        log(f"   ⚠️ Could not fetch commit history: {e}")

    # Remove the .git folder immediately to save disk space and prevent recursive scans
    git_folder = os.path.join(tmp_dir, ".git")
    if os.path.exists(git_folder):
        import stat
        # Windows sometimes throws permission errors if git files are read-only
        for root, dirs, files in os.walk(git_folder):
            for fname in files:
                full_path = os.path.join(root, fname)
                os.chmod(full_path, stat.S_IWRITE)
        shutil.rmtree(git_folder, ignore_errors=True)
        log("🧹 Removed .git metadata directory to save space.")

    return tmp_dir, git_metadata


# ============================================================================
# AUTHENTICATION & RBAC (JWT)
# ============================================================================

JWT_SECRET = os.environ.get("JWT_SECRET", "ministry-plagiarism-secret-key-change-in-production")
if JWT_SECRET == "ministry-plagiarism-secret-key-change-in-production":
    import warnings
    warnings.warn("Using default JWT secret! Set JWT_SECRET environment variable in production.", stacklevel=2)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

_bearer_scheme = HTTPBearer()


def _create_access_token(user_id: str, email: str, role: str, requires_password_change: bool = False) -> str:
    """Build a signed JWT containing the user identity, role, and password-change flag."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "requires_password_change": bool(requires_password_change),
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class LoginRequest(BaseModel):
    """
    Login now accepts a generic `identifier`: an email for staff/admin accounts
    (users table) or an enrollment number for student accounts (students table).

    `email` is kept as a backwards-compatible alias so existing clients
    (streamlit_app.py, frontend/src/lib/api.ts) keep working unchanged.
    """
    identifier: Optional[str] = None
    email: Optional[str] = None
    password: str

    def resolve_identifier(self) -> str:
        """Return the effective login identifier, whichever field was supplied."""
        return (self.identifier or self.email or "").strip()


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def require_role(*allowed_roles: str):
    """
    FastAPI dependency enforcing JWT + role-based access control.

    Reads the 'Authorization: Bearer <token>' header, decodes the JWT, and
    extracts user_id / role. Raises 401 on invalid credentials and 403 when
    the authenticated role is not permitted.
    """
    def _enforce(credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)):
        try:
            payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = payload.get("user_id")
        role = payload.get("role")
        email = payload.get("email")

        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        if allowed_roles and role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "requires_password_change": bool(payload.get("requires_password_change")),
        }

    return _enforce


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    db = get_db()
    identifier = payload.resolve_identifier()

    if not identifier:
        raise HTTPException(status_code=400, detail="Identifier (email or enrollment number) is required")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")

    # Unified lookup: staff/admin by email, then student by enrollment_number.
    user = db.get_user_or_student_by_login(identifier)

    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid identifier or password")

    try:
        password_matches = bcrypt.checkpw(
            payload.password.encode("utf-8"), user["password_hash"].encode("utf-8")
        )
    except ValueError:
        # Malformed / non-bcrypt hash stored on the record.
        password_matches = False

    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid identifier or password")

    is_student = bool(user.get("is_student")) or user.get("role") == "student"
    requires_password_change = bool(user.get("requires_password_change"))

    token = _create_access_token(user["id"], user["email"], user["role"], requires_password_change)

    response_user = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "requires_password_change": requires_password_change,
    }
    if is_student:
        response_user["enrollment_number"] = user.get("enrollment_number")

    return {"token": token, "user": response_user}


@app.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(require_role())):
    db = get_db()
    user = db.get_user_by_id(current_user["user_id"])
    if user:
        return {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "college_id": user.get("college_id"),
            "requires_password_change": bool(user.get("requires_password_change")),
            "created_at": user.get("created_at"),
        }

    # Student tokens resolve against the students table instead.
    student = db.get_student_by_id(current_user["user_id"])
    if not student:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": student["id"],
        "name": student["name"],
        "email": student.get("enrollment_number"),
        "enrollment_number": student.get("enrollment_number"),
        "role": "student",
        "college_id": student.get("college_id"),
        "team_id": student.get("team_id"),
        "requires_password_change": bool(student.get("requires_password_change")),
        "created_at": student.get("created_at"),
    }


@app.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(require_role()),
):
    """
    Rotate the caller's own password. Works for both staff/admin accounts
    (users table) and student accounts (students table) and clears the
    forced `requires_password_change` flag on success.
    """
    db = get_db()
    user_id = current_user["user_id"]

    if not payload.old_password:
        raise HTTPException(status_code=400, detail="Old password is required")
    if not payload.new_password:
        raise HTTPException(status_code=400, detail="New password is required")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the old password")

    is_student = False
    account = db.get_user_by_id(user_id)
    if not account:
        account = db.get_student_by_id(user_id)
        is_student = True
    if not account:
        raise HTTPException(status_code=404, detail="User not found")

    stored_hash = account.get("password_hash")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="No password is set for this account")

    try:
        verified = bcrypt.checkpw(payload.old_password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        verified = False

    if not verified:
        raise HTTPException(status_code=401, detail="Incorrect old password")

    new_hash = bcrypt.hashpw(payload.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    if is_student:
        db.update_student(user_id, password_hash=new_hash, requires_password_change=0)
        identifier = account.get("enrollment_number")
        role = "student"
    else:
        db.update_user(user_id, password_hash=new_hash, requires_password_change=0)
        identifier = account.get("email")
        role = account.get("role")

    # Re-issue the token so the client drops the forced password-change state.
    token = _create_access_token(user_id, identifier, role, False)

    return {
        "detail": "Password updated successfully",
        "requires_password_change": False,
        "token": token,
    }


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


@app.get("/api/teams", dependencies=[Depends(require_role())])
async def list_teams(college_id: Optional[str] = None):
    db = get_db()
    return {"teams": db.get_all_teams(college_id)}


@app.post("/api/teams", dependencies=[Depends(require_role())])
async def create_team(payload: TeamCreate):
    db = get_db()
    team_id = str(uuid.uuid4())
    db.create_team(team_id, payload.name, payload.college_id)
    team = db.get_team_by_id(team_id)
    return team


@app.get("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def get_team(team_id: str):
    db = get_db()
    team = db.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = db.get_team_members(team_id)
    return {**team, "members": members}


@app.put("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def update_team(team_id: str, payload: TeamUpdate):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.update_team(team_id, name=payload.name)
    return db.get_team_by_id(team_id)


@app.delete("/api/teams/{team_id}", dependencies=[Depends(require_role())])
async def delete_team(team_id: str):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete_team(team_id)
    return {"detail": "Team deleted"}


@app.post("/api/teams/{team_id}/members", dependencies=[Depends(require_role())])
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


@app.delete("/api/teams/{team_id}/members/{student_id}", dependencies=[Depends(require_role())])
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


# ============================================================================
# USERS CRUD
# ============================================================================

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    college_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    college_id: Optional[str] = None
    requires_password_change: Optional[bool] = None


def _serialize_user(user: dict) -> dict:
    """Strip password_hash from user responses."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "college_id": user.get("college_id"),
        "requires_password_change": bool(user.get("requires_password_change")),
        "created_at": user.get("created_at"),
    }


@app.get("/api/users", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def list_users(role: Optional[str] = None, college_id: Optional[str] = None):
    db = get_db()
    users = db.get_all_users(role_filter=role)
    if college_id is not None:
        users = [u for u in users if u.get("college_id") == college_id]
    return {"users": [_serialize_user(u) for u in users]}


@app.post("/api/users")
async def create_user_endpoint(
    payload: UserCreate,
    current_user: dict = Depends(require_role("ministry_admin", "college_admin")),
):
    db = get_db()
    email = payload.email.strip().lower()
    name = payload.name.strip()

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")

    valid_roles = {"ministry_admin", "college_admin", "student"}
    if payload.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")

    user_id = str(uuid.uuid4())

    # --- Admin Self-Lock -------------------------------------------------
    # An admin can never create/re-register their own account under a different
    # role (self role change / privilege escalation or demotion).
    if current_user["user_id"] == user_id and current_user["role"] != payload.role:
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")

    self_record = db.get_user_by_id(current_user["user_id"])
    if self_record and self_record.get("email") == email and current_user["role"] != payload.role:
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    # ---------------------------------------------------------------------

    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.create_user(user_id, name, email, password_hash, payload.role, payload.college_id)
    user = db.get_user_by_id(user_id)
    return _serialize_user(user)


@app.get("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def get_user(user_id: str):
    db = get_db()
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@app.put("/api/users/{user_id}")
async def update_user_endpoint(
    user_id: str,
    payload: UserUpdate,
    current_user: dict = Depends(require_role("ministry_admin", "college_admin")),
):
    db = get_db()
    existing = db.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # --- Admin Self-Lock -------------------------------------------------
    # Admins are forbidden from modifying their own role. The check only fires
    # when a role change is actually requested, so admins can still update their
    # own name / password / college assignment.
    if payload.role is not None and current_user["user_id"] == user_id and current_user["role"] != payload.role:
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    # ---------------------------------------------------------------------

    if payload.email is not None:
        email = payload.email.strip().lower()
        other = db.get_user_by_email(email)
        if other and other["id"] != user_id:
            raise HTTPException(status_code=400, detail="Email already registered")

    fields: Dict[str, Any] = {}
    if payload.name is not None:
        fields["name"] = payload.name.strip()
    if payload.email is not None:
        fields["email"] = payload.email.strip().lower()
    if payload.password is not None:
        fields["password_hash"] = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    if payload.role is not None:
        valid_roles = {"ministry_admin", "college_admin", "student"}
        if payload.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")
        fields["role"] = payload.role
    if payload.college_id is not None:
        fields["college_id"] = payload.college_id
    if payload.requires_password_change is not None:
        # Lets an admin force a staff account to reset its password at next login.
        fields["requires_password_change"] = payload.requires_password_change

    if fields:
        db.update_user(user_id, **fields)

    return _serialize_user(db.get_user_by_id(user_id))


@app.delete("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def delete_user_endpoint(user_id: str):
    db = get_db()
    existing = db.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete_user(user_id)
    return {"detail": "User deleted"}


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/api/system/health")
async def health_check():
    return {
        "status": "healthy",
        "biometrics": "not_available",
        "plagiarism": "operational",
        "models_ready": _models_ready,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


@app.get("/api/plagiarism/projects", dependencies=[Depends(require_role())])
async def list_projects():
    db = get_db()
    projects = db.get_all_projects()

    # The Faculty Approval UI drives off `status`, and students may only see
    # their own submissions via `student_id`. Guarantee both keys exist on every
    # row (older rows predate the student_id column and may hold NULLs).
    serialized = []
    for project in projects:
        item = dict(project)
        if not item.get("status"):
            item["status"] = "approved"
        item.setdefault("student_id", None)
        serialized.append(item)

    return {"projects": serialized}


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    abstract: Optional[str] = None
    team_id: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None
    university: Optional[str] = None
    status: Optional[str] = None


@app.put("/api/plagiarism/projects/{project_id}", dependencies=[Depends(require_role())])
async def update_project(project_id: str, payload: ProjectUpdate):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    db.update_project(
        project_id,
        title=payload.title,
        abstract=payload.abstract,
        team_id=payload.team_id,
        department=payload.department,
        year=payload.year,
        university=payload.university,
        status=payload.status,
    )
    return db.get_project_by_id(project_id)


@app.post("/api/plagiarism/projects/{project_id}/approve", dependencies=[Depends(require_role("ministry_admin", "college_admin", "faculty"))])
async def approve_project(project_id: str):
    """Faculty approval workflow: flip a pending project's status to 'approved'."""
    db = get_db()
    conn = db._get_connection()
    try:
        cursor = conn.cursor()
        # psycopg2 and sqlite3 use different parameter placeholders.
        placeholder = "%s" if db.mode == "postgresql" else "?"
        cursor.execute(f"UPDATE projects SET status = 'approved' WHERE id = {placeholder}", (project_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            raise HTTPException(404, "Project not found")
        conn.commit()
    finally:
        conn.close()
    return {"detail": "Project approved successfully"}


@app.delete("/api/plagiarism/projects/{project_id}", dependencies=[Depends(require_role())])
async def delete_project(project_id: str):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete_project(project_id)

    # Clean up the project's embeddings from the FAISS vector store as well.
    # Runs in an executor so index I/O never blocks the event loop; a failure
    # here must not fail the (already completed) DB deletion.
    try:
        vstore = get_vstore()
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: vstore.delete_project(project_id)
        )
    except Exception as e:
        print(f"FAISS cleanup warning for project '{project_id}': {e}")

    return {"detail": "Project deleted"}


@app.get("/api/plagiarism/projects/{project_id}/files", dependencies=[Depends(require_role())])
async def list_project_files(project_id: str):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    files = db.get_project_files(project_id)
    return {"files": files}


@app.get("/api/plagiarism/projects/check")
async def check_projects(names: str):
    name_list = [n.strip() for n in names.split(",") if n.strip()]
    db = get_db()
    existing = db.check_project_exists(name_list)
    return existing


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


@app.get("/api/plagiarism/history", dependencies=[Depends(require_role())])
async def get_scan_history():
    """Return every stored scan report as a lightweight summary list."""
    history = _load_history()
    return {"reports": [_history_summary(entry) for entry in history]}


@app.get("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role())])
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


@app.delete("/api/plagiarism/history/{report_id}", dependencies=[Depends(require_role())])
async def delete_scan_history_report(report_id: str):
    """Delete a single stored scan report."""
    history = _load_history()
    remaining = [entry for entry in history if entry.get("id") != report_id]
    if len(remaining) == len(history):
        raise HTTPException(status_code=404, detail=f"Scan report '{report_id}' not found")
    _save_history(remaining)
    return {"status": "success", "message": f"Scan report '{report_id}' deleted"}


# --- Upload + Scan (JSON response) ---
@app.post("/api/plagiarism/upload-scan", dependencies=[Depends(require_role())])
async def upload_and_scan(
    project_name: str = Form(...),
    scan_type: str = Form("Direct Upload Project Scan"),
    files: List[UploadFile] = File(...),
):
    extracted_files = []
    for upload_file in files:
        content = (await upload_file.read()).decode("utf-8", errors="ignore")
        filename = upload_file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        file_type = FileExtractor.categorize_file(filename)
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
@app.post("/api/plagiarism/upload-scan-stream", dependencies=[Depends(require_role())])
async def upload_and_scan_stream(
    project_name: str = Form(...),
    scan_type: str = Form("Direct Upload Project Scan"),
    files: List[UploadFile] = File(...),
):
    # Read files synchronously first
    extracted_files = []
    for upload_file in files:
        raw = await upload_file.read()
        content = raw.decode("utf-8", errors="ignore")
        filename = upload_file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        file_type = FileExtractor.categorize_file(filename)
        extracted_files.append({
            "relative_path": filename,
            "filename": Path(filename).name,
            "extension": ext,
            "file_type": file_type,
            "content": content,
        })

    async def event_stream():
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "log", "text": msg})

        def run_intake():
            try:
                res = _run_intake(project_name, extracted_files, log_callback=log_callback)
                loop.call_soon_threadsafe(q.put_nowait, {"type": "complete", "result": res})
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "message": str(e)})

        # Start the background thread
        executor_task = loop.run_in_executor(None, run_intake)

        while True:
            event = await q.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Upload + Scan ZIP Archive (SSE Streaming) ---
@app.post("/api/plagiarism/upload-zip-stream", dependencies=[Depends(require_role())])
async def upload_zip_stream(
    project_name: str = Form(...),
    scan_type: str = Form("ZIP Archive Scan"),
    file: UploadFile = File(...),
):
    import zipfile

    tmp_dir = tempfile.mkdtemp(prefix="plagiarism_zip_")

    async def event_stream():
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "log", "text": msg})

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
                loop.call_soon_threadsafe(q.put_nowait, {"type": "complete", "result": res})
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "message": str(e)})
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        executor_task = loop.run_in_executor(None, run_zip_intake)

        while True:
            event = await q.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
# --- Git Repo Scan (JSON) ---
@app.post("/api/plagiarism/git-scan", dependencies=[Depends(require_role())])
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
@app.post("/api/plagiarism/git-scan-stream", dependencies=[Depends(require_role())])
async def git_scan_stream(payload: GitScanRequest):

    async def event_stream():
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def log_callback(msg: str):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "log", "text": msg})

        def run_git_intake():
            tmp_dir = None
            try:
                tmp_dir, git_metadata = _clone_git_repo(
                    payload.repo_url, payload.branch or "main", payload.access_token, log_callback=log_callback
                )

                project_name = payload.project_name or Path(payload.repo_url.rstrip("/")).stem
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
                loop.call_soon_threadsafe(q.put_nowait, {"type": "complete", "result": res})
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "message": str(e)})
            finally:
                if tmp_dir:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

        executor_task = loop.run_in_executor(None, run_git_intake)

        while True:
            event = await q.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Named scan on already-indexed project ---
@app.post("/api/plagiarism/scan", dependencies=[Depends(require_role())])
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


@app.get("/api/dashboard/stats")
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


class DeepScanRequest(BaseModel):
    # `project_id` is the baseline (source) project the report was produced from.
    # `project_name` / `target` are accepted as aliases so callers that only know
    # the project name (e.g. a report loaded from history) still work.
    project_id: Optional[str] = None
    file1_path: str
    other_project_id: Optional[str] = None
    file2_path: str
    project_name: Optional[str] = None
    target: Optional[str] = None


def _cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two 1-D vectors using numpy."""
    import numpy as np

    a = np.asarray(a, dtype="float32").flatten()
    b = np.asarray(b, dtype="float32").flatten()
    denom = (float(np.linalg.norm(a) * np.linalg.norm(b))) or 1.0
    return float(np.dot(a, b) / denom)


def _resolve_file_type(relative_path: str) -> str:
    """Return 'code' or 'text' based on the file extension."""
    from plagiarism_engine.extractor import CODE_EXTENSIONS

    ext = Path(relative_path).suffix.lower()
    return "code" if ext in CODE_EXTENSIONS else "text"


@app.post("/api/plagiarism/deep-scan", dependencies=[Depends(require_role())])
async def deep_scan(req: DeepScanRequest):
    db = get_db()

    # --- 0. Resolve the baseline project id from the JSON payload -----------
    project_id = (req.project_id or req.project_name or req.target or "").strip()
    other_project_id = (req.other_project_id or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'project_id' (the baseline project) in the request payload.",
        )
    if not other_project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'other_project_id' (the matched project) in the request payload.",
        )
    if not req.file1_path or not req.file2_path:
        raise HTTPException(
            status_code=400,
            detail="Both 'file1_path' and 'file2_path' are required.",
        )

    # --- 1. Load both files' content from the database ----------------------
    files1 = db.get_project_files(project_id)
    files2 = db.get_project_files(other_project_id)

    if not files1:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found in database")
    if not files2:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{other_project_id}' not found in database",
        )

    file1 = next((f for f in files1 if f.get("relative_path") == req.file1_path), None)
    file2 = next((f for f in files2 if f.get("relative_path") == req.file2_path), None)

    if file1 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file1_path}' not found in project '{project_id}'",
        )
    if file2 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file2_path}' not found in project '{other_project_id}'",
        )

    content1 = file1.get("content", "") or ""
    content2 = file2.get("content", "") or ""
    if not content1.strip() or not content2.strip():
        raise HTTPException(status_code=400, detail="Both files must have non-empty content")

    # --- 2. Determine file type by extension --------------------------------
    # Use the stored file_type when present; otherwise derive from extension.
    ftype1 = file1.get("file_type") or _resolve_file_type(req.file1_path)
    ftype2 = file2.get("file_type") or _resolve_file_type(req.file2_path)

    # Use the first file's type to pick the model. If the two disagreed, base
    # the choice on the pair's dominant type (code wins only when both are code).
    if ftype1 == "code" and ftype2 == "code":
        file_type = "code"
    else:
        file_type = "text"

    # --- 3/4. Load model + encode + compute cosine similarity --------------
    model_name = "unixcoder-base" if file_type == "code" else "bge-m3"
    try:
        model = _get_deep_scan_model(model_name)
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: model.encode(
                [content1, content2],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        )
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="SentenceTransformer model is not downloaded yet. Please wait.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep scan failed: {str(e)}")

    similarity_pct = round(similarity * 100, 2)
    verdict = "CONFIRMED_PLAGIARISM" if similarity > 0.85 else "LIKELY_ORIGINAL"

    return {
        "ai_similarity": similarity_pct,
        "model_used": model_name,
        "method": "cosine_similarity",
        "verdict": verdict,
        "file1": req.file1_path,
        "file2": req.file2_path,
    }


class BulkDeepScanRequest(BaseModel):
    project_id: str


@app.post("/api/plagiarism/deep-scan-bulk", dependencies=[Depends(require_role())])
async def deep_scan_bulk(req: BulkDeepScanRequest):
    """FAISS bulk semantic scan: top-5 cross-project matches for every file of a project."""
    project_id = (req.project_id or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail="Missing 'project_id' in the request payload.",
        )

    db = get_db()
    if not db.get_project_by_id(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found in database",
        )

    vstore = get_vstore()
    try:
        matches = await asyncio.get_event_loop().run_in_executor(
            None, lambda: vstore.search_bulk(project_id)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk deep scan failed: {str(e)}")

    return {
        "project_id": project_id,
        "match_count": len(matches),
        "matches": matches,
    }


class ProjectComparisonRequest(BaseModel):
    project_a: str
    project_b: str


def _run_project_comparison(project_a: str, project_b: str) -> List[Dict[str, Any]]:
    """Compare project_a against ONLY project_b using the fingerprint index.

    For every file in project_a, queries the shared fingerprint index and
    keeps only candidates belonging to project_b. Similarity is the overlap
    coefficient: shared / min(file_a_fps, file_b_fps), which also catches
    small files pasted inside larger ones. Matches below 20% are dropped
    and results are sorted by highest similarity first.
    """
    db = get_db()
    project_files = db.get_project_files(project_a)
    file_fingerprints = db.get_project_fingerprints(project_a)

    comparisons: List[Dict[str, Any]] = []
    prefix = f"{project_b}::"

    for f in project_files:
        rel_path = f.get("relative_path", "")
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if not rel_path or not fps or ftype not in ("code", "text"):
            continue

        fp_hashes = [h for h, _p in fps]
        total_a_fps = len(fp_hashes)
        if not total_a_fps:
            continue

        candidates = db.query_candidates(fp_hashes, ftype, project_a)

        for key, shared in candidates.items():
            # Restrict results STRICTLY to project_b.
            if not key.startswith(prefix):
                continue
            other_path = key[len(prefix):]

            total_b_fps = db.get_file_fingerprint_count(project_b, other_path)
            if not total_b_fps:
                continue

            # Overlap coefficient: shared / min(source, target)
            sim_val = min(shared / min(total_a_fps, total_b_fps), 1.0)
            if sim_val < 0.20:  # Filter out weak matches below 20%
                continue

            comparisons.append({
                "file_a": rel_path,
                "file_b": other_path,
                "similarity": round(sim_val * 100, 2),
                "type": ftype,
            })

    comparisons.sort(key=lambda c: c["similarity"], reverse=True)
    return comparisons


@app.post("/api/plagiarism/compare-projects", dependencies=[Depends(require_role())])
async def compare_projects(req: ProjectComparisonRequest):
    """Direct project-to-project comparison: overlap matrix of matching files."""
    project_a = (req.project_a or "").strip()
    project_b = (req.project_b or "").strip()
    if not project_a or not project_b:
        raise HTTPException(
            status_code=400,
            detail="Both 'project_a' and 'project_b' are required.",
        )
    if project_a == project_b:
        raise HTTPException(
            status_code=400,
            detail="'project_a' and 'project_b' must be different projects.",
        )

    db = get_db()
    if not db.get_project_by_id(project_a):
        raise HTTPException(status_code=404, detail=f"Project '{project_a}' not found in database")
    if not db.get_project_by_id(project_b):
        raise HTTPException(status_code=404, detail=f"Project '{project_b}' not found in database")

    try:
        comparisons = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_project_comparison(project_a, project_b)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project comparison failed: {str(e)}")

    return {
        "status": "completed",
        "project_a": project_a,
        "project_b": project_b,
        "match_count": len(comparisons),
        "comparisons": comparisons,
    }


class CompareFilesRequest(BaseModel):
    project_a: str
    file_a: str
    project_b: str
    file_b: str


def _resolve_stored_file(project_id: str, relative_path: str) -> Optional[str]:
    """Return the text content of one stored project file, or None if absent.

    Looks on disk first (``data/project_files/<project>/<relative_path>``) and
    then falls back to the database copy, which is where uploaded archives are
    actually kept by ``db.save_project()``. The resolved path is verified to stay
    inside the project folder so a crafted ``relative_path`` cannot escape it.
    """
    # --- 1. On-disk copy -----------------------------------------------------
    project_root = os.path.realpath(
        os.path.join(str(DATA_DIR), "project_files", project_id)
    )
    candidate = os.path.realpath(os.path.join(project_root, relative_path))
    if candidate.startswith(project_root + os.sep) and os.path.isfile(candidate):
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            pass

    # --- 2. Database copy (compressed project_files table) -------------------
    db = get_db()
    for f in db.get_project_files(project_id):
        if f.get("relative_path") == relative_path:
            return f.get("content", "") or ""
    return None


@app.post("/api/plagiarism/compare-files", dependencies=[Depends(require_role())])
async def compare_files_endpoint(req: CompareFilesRequest):
    """Line-level diff of two stored files, used by the visual Diff Viewer.

    Returns both files split into lines plus the raw ``difflib`` opcodes
    ``(tag, i1, i2, j1, j2)``; the frontend highlights every ``equal`` block
    because identical lines are the plagiarism evidence.
    """
    project_a = (req.project_a or "").strip()
    project_b = (req.project_b or "").strip()
    file_a = (req.file_a or "").strip()
    file_b = (req.file_b or "").strip()
    if not project_a or not project_b or not file_a or not file_b:
        raise HTTPException(
            status_code=400,
            detail="'project_a', 'file_a', 'project_b' and 'file_b' are all required.",
        )

    def _load() -> tuple:
        return (
            _resolve_stored_file(project_a, file_a),
            _resolve_stored_file(project_b, file_b),
        )

    content_a, content_b = await asyncio.get_event_loop().run_in_executor(None, _load)

    if content_a is None or content_b is None:
        missing = []
        if content_a is None:
            missing.append(f"'{file_a}' in project '{project_a}'")
        if content_b is None:
            missing.append(f"'{file_b}' in project '{project_b}'")
        raise HTTPException(404, f"One or both files not found on disk: {', '.join(missing)}")

    lines_a = content_a.splitlines()
    lines_b = content_b.splitlines()

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    opcodes = matcher.get_opcodes()  # list of tuples: (tag, i1, i2, j1, j2)
    matched_lines = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")

    return {
        "project_a": project_a,
        "project_b": project_b,
        "file_a": file_a,
        "file_b": file_b,
        "lines_a": lines_a,
        "lines_b": lines_b,
        "opcodes": opcodes,
        "matched_lines": matched_lines,
        "match_ratio": round(matcher.ratio() * 100, 2),
    }


@app.get("/api/settings")
async def get_settings():
    db = get_db()
    return db.get_all_settings()


@app.put("/api/settings", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def update_settings(payload: Dict[str, Any]):
    db = get_db()
    db.update_settings(payload)
    return db.get_all_settings()
