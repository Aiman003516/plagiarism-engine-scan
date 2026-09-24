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
import sys
import time
import uuid
import json
import shutil
import tempfile
import subprocess
import asyncio
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
    MultilingualVectorStore,
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
    except Exception:
        pass
    _models_ready = True


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Singletons (cached)
# ---------------------------------------------------------------------------
_db: Optional[SystemDBStore] = None
_vstore: Optional[MultilingualVectorStore] = None

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


def get_vstore() -> MultilingualVectorStore:
    global _vstore
    if _vstore is None:
        _vstore = MultilingualVectorStore(
            collection_name="plagiarism_vector_db",
            persist_directory=str(DATA_DIR / "chroma_db"),
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
        except Exception:
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
    vstore = get_vstore()
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

    try:
        vstore.index_project_files(project_files=project_files, project_id=project_name)
    except Exception as e:
        log(f"   ⚠️ Vector indexing warning: {e}")

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

    log("💾 Storing new fingerprints to database index...")
    for f in project_files:
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if fps:
            db.store_fingerprints(project_name, rel_path, ftype, fps)

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

    log(f"[PHASE 1/2] 📂 Loading project '{project_name}' from database...")
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

    log("[PHASE 2/2] 🔍 Querying fingerprint index for candidates...")
    
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
            
            # Simple overlap coefficient: shared / total in source file
            sim_val = count / total_fps
            
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
            ["git", "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=400, detail=f"Git clone failed: {e.stderr}")
    except FileNotFoundError:
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
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

_bearer_scheme = HTTPBearer()


def _create_access_token(user_id: str, email: str, role: str) -> str:
    """Build a signed JWT containing the user identity and role."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "college_admin"


class LoginRequest(BaseModel):
    email: str
    password: str


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

        return {"user_id": user_id, "email": email, "role": role}

    return _enforce


@app.post("/api/auth/register")
async def register(payload: RegisterRequest):
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

    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())
    db.create_user(user_id, name, email, password_hash, payload.role, None)

    token = _create_access_token(user_id, email, payload.role)
    return {
        "token": token,
        "user": {"id": user_id, "name": name, "email": email, "role": payload.role},
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    db = get_db()
    email = payload.email.strip().lower()
    user = db.get_user_by_email(email)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(payload.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_access_token(user["id"], user["email"], user["role"])
    return {
        "token": token,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }


@app.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(require_role())):
    db = get_db()
    user = db.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "college_id": user.get("college_id"),
        "created_at": user.get("created_at"),
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


@app.get("/api/teams")
async def list_teams(college_id: Optional[str] = None):
    db = get_db()
    return {"teams": db.get_all_teams(college_id)}


@app.post("/api/teams")
async def create_team(payload: TeamCreate):
    db = get_db()
    team_id = str(uuid.uuid4())
    db.create_team(team_id, payload.name, payload.college_id)
    team = db.get_team_by_id(team_id)
    return team


@app.get("/api/teams/{team_id}")
async def get_team(team_id: str):
    db = get_db()
    team = db.get_team_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = db.get_team_members(team_id)
    return {**team, "members": members}


@app.put("/api/teams/{team_id}")
async def update_team(team_id: str, payload: TeamUpdate):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.update_team(team_id, name=payload.name)
    return db.get_team_by_id(team_id)


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str):
    db = get_db()
    existing = db.get_team_by_id(team_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete_team(team_id)
    return {"detail": "Team deleted"}


@app.post("/api/teams/{team_id}/members")
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


@app.delete("/api/teams/{team_id}/members/{student_id}")
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


def _serialize_user(user: dict) -> dict:
    """Strip password_hash from user responses."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "college_id": user.get("college_id"),
        "created_at": user.get("created_at"),
    }


@app.get("/api/users", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def list_users(role: Optional[str] = None, college_id: Optional[str] = None):
    db = get_db()
    users = db.get_all_users(role_filter=role)
    if college_id is not None:
        users = [u for u in users if u.get("college_id") == college_id]
    return {"users": [_serialize_user(u) for u in users]}


@app.post("/api/users", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def create_user_endpoint(payload: UserCreate):
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

    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = str(uuid.uuid4())
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


@app.put("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def update_user_endpoint(user_id: str, payload: UserUpdate):
    db = get_db()
    existing = db.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

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


@app.get("/api/plagiarism/projects")
async def list_projects():
    db = get_db()
    projects = db.get_all_projects()
    return {"projects": projects}


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    abstract: Optional[str] = None
    team_id: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None
    university: Optional[str] = None
    status: Optional[str] = None


@app.put("/api/plagiarism/projects/{project_id}")
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


@app.delete("/api/plagiarism/projects/{project_id}")
async def delete_project(project_id: str):
    db = get_db()
    existing = db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete_project(project_id)
    return {"detail": "Project deleted"}


@app.get("/api/plagiarism/projects/{project_id}/files")
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


# --- Upload + Scan (JSON response) ---
@app.post("/api/plagiarism/upload-scan")
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

    result = _run_intake(project_name, extracted_files)
    return result


# --- Upload + Scan (SSE Streaming) ---
@app.post("/api/plagiarism/upload-scan-stream")
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
        logs = []

        def log_callback(msg: str):
            logs.append(msg)

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _run_intake(project_name, extracted_files, log_callback=log_callback),
            )

            # Emit all logs
            for log_msg in logs:
                yield f"data: {json.dumps({'type': 'log', 'text': log_msg})}\n\n"
                await asyncio.sleep(0.01)

            # Emit final result
            yield f"data: {json.dumps({'type': 'complete', 'result': result}, default=str)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Upload + Scan ZIP Archive (SSE Streaming) ---
@app.post("/api/plagiarism/upload-zip-stream")
async def upload_zip_stream(
    project_name: str = Form(...),
    scan_type: str = Form("ZIP Archive Scan"),
    file: UploadFile = File(...),
):
    import zipfile

    tmp_dir = tempfile.mkdtemp(prefix="plagiarism_zip_")

    async def event_stream():
        logs = []
        def log_callback(msg: str):
            logs.append(msg)

        try:
            log_callback(f"📦 Extracting ZIP archive '{file.filename}'...")
            zip_path = os.path.join(tmp_dir, "upload.zip")
            with open(zip_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            log_callback(f"📂 Scanning extracted project directory: {project_name}...")
            extracted_files = FileExtractor.scan_project_directory(extract_dir)
            
            for f in extracted_files:
                if "relative_path" not in f:
                    f["relative_path"] = f.get("filename", "")

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _run_intake(project_name, extracted_files, log_callback=log_callback),
            )

            for log_msg in logs:
                yield f"data: {json.dumps({'type': 'log', 'text': log_msg})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'type': 'complete', 'result': result}, default=str)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
# --- Git Repo Scan (JSON) ---
@app.post("/api/plagiarism/git-scan")
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
@app.post("/api/plagiarism/git-scan-stream")
async def git_scan_stream(payload: GitScanRequest):

    async def event_stream():
        logs = []

        def log_callback(msg: str):
            logs.append(msg)

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

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _run_intake(
                    project_name, extracted_files,
                    log_callback=log_callback,
                    git_metadata=git_metadata,
                ),
            )

            for log_msg in logs:
                yield f"data: {json.dumps({'type': 'log', 'text': log_msg})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'type': 'complete', 'result': result}, default=str)}\n\n"

        except Exception as e:
            for log_msg in logs:
                yield f"data: {json.dumps({'type': 'log', 'text': log_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Named scan on already-indexed project ---
@app.post("/api/plagiarism/scan")
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
    recent_scans = history[-10:] if history else []
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
    project_id: str
    file1_path: str
    other_project_id: str
    file2_path: str


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


@app.post("/api/plagiarism/deep-scan")
async def deep_scan(req: DeepScanRequest):
    db = get_db()

    # --- 1. Load both files' content from the database ----------------------
    files1 = db.get_project_files(req.project_id)
    files2 = db.get_project_files(req.other_project_id)

    file1 = next((f for f in files1 if f.get("relative_path") == req.file1_path), None)
    file2 = next((f for f in files2 if f.get("relative_path") == req.file2_path), None)

    if file1 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file1_path}' not found in project '{req.project_id}'",
        )
    if file2 is None:
        raise HTTPException(
            status_code=404,
            detail=f"File '{req.file2_path}' not found in project '{req.other_project_id}'",
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
        embeddings = model.encode(
            [content1, content2],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        similarity = _cosine_similarity(embeddings[0], embeddings[1])
    except FileNotFoundError:
        raise
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


@app.get("/api/settings")
async def get_settings():
    db = get_db()
    return db.get_all_settings()


@app.put("/api/settings", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def update_settings(payload: Dict[str, Any]):
    db = get_db()
    db.update_settings(payload)
    return db.get_all_settings()
