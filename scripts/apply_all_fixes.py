"""
Comprehensive remediation script applying all verified fixes for system_deep_audit_report.md.
"""

import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def patch_file(filepath: Path, patches: list[tuple[str, str]]):
    print(f"Patching {filepath.relative_to(BASE_DIR)}...")
    content = filepath.read_text(encoding="utf-8")
    for old, new in patches:
        if old not in content:
            print(f"  [WARNING] Target substring not found in {filepath.name}:")
            print(f"    {repr(old[:60])}...")
            # Check if already patched
            if new in content:
                print(f"  [INFO] Already patched!")
                continue
            raise RuntimeError(f"Failed to find target in {filepath.name}")
        content = content.replace(old, new, 1)
        print(f"  [OK] Applied replacement")
    filepath.write_text(content, encoding="utf-8")

def main():
    # ------------------------------------------------------------------------
    # 1. plagiarism_engine/db/helpers.py: Upgrade decompress_text
    # ------------------------------------------------------------------------
    p_helpers = BASE_DIR / "plagiarism_engine" / "db" / "helpers.py"
    old_decompress = """def decompress_text(b64_text: str) -> str:
    if not b64_text:
        return ""
    try:
        return zlib.decompress(base64.b64decode(b64_text.encode('utf-8'))).decode('utf-8')
    except Exception:
        return b64_text"""
    new_decompress = """def decompress_text(data: Any) -> str:
    if not data:
        return ""
    if isinstance(data, (bytes, bytearray, memoryview)):
        raw_bytes = bytes(data)
        try:
            return zlib.decompress(raw_bytes).decode('utf-8', errors='replace')
        except Exception:
            try:
                return zlib.decompress(base64.b64decode(raw_bytes)).decode('utf-8', errors='replace')
            except Exception:
                return raw_bytes.decode('utf-8', errors='replace')
    s = str(data)
    try:
        decoded_bytes = base64.b64decode(s.encode('utf-8'))
        return zlib.decompress(decoded_bytes).decode('utf-8', errors='replace')
    except Exception:
        return s"""
    patch_file(p_helpers, [(old_decompress, new_decompress)])

    # ------------------------------------------------------------------------
    # 2. plagiarism_engine/extractor.py: Symlink traversal prevention
    # ------------------------------------------------------------------------
    p_extractor = BASE_DIR / "plagiarism_engine" / "extractor.py"
    old_extractor_loop = """        for root, dirs, files in os.walk(dir_path):
            if size_exceeded:
                break
            dirs[:] = [d for d in dirs if d.lower() not in ignored_d and not d.startswith('.')]

            for file in files:
                file_name_lower = file.lower()
                if file_name_lower in ignored_f:
                    continue

                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(dir_path))"""
    new_extractor_loop = """        for root, dirs, files in os.walk(dir_path):
            if size_exceeded:
                break
            dirs[:] = [
                d for d in dirs
                if d.lower() not in ignored_d and not d.startswith('.') and not os.path.islink(os.path.join(root, d))
            ]

            for file in files:
                file_name_lower = file.lower()
                if file_name_lower in ignored_f:
                    continue

                file_path = Path(root) / file
                if os.path.islink(file_path):
                    continue
                rel_path = str(file_path.relative_to(dir_path))"""
    patch_file(p_extractor, [(old_extractor_loop, new_extractor_loop)])

    # ------------------------------------------------------------------------
    # 3. plagiarism_engine/storage/supabase_storage.py: Path traversal prevention
    # ------------------------------------------------------------------------
    p_supa_storage = BASE_DIR / "plagiarism_engine" / "storage" / "supabase_storage.py"
    old_supa_init = """    def __init__(self, url: str, key: str, bucket: str = "project-files"):"""
    new_supa_init = """    @staticmethod
    def _validate_safe_path(p: str) -> str:
        clean = p.replace("\\\\", "/").strip().lstrip("/")
        parts = clean.split("/")
        if ".." in parts or any(part == "." for part in parts):
            raise ValueError(f"Unsafe path traversal detected: {p}")
        return clean

    def __init__(self, url: str, key: str, bucket: str = "project-files"):"""
    old_supa_save = """    def save_file(self, path: str, content: bytes) -> str:
        clean_path = path.lstrip("/")"""
    new_supa_save = """    def save_file(self, path: str, content: bytes) -> str:
        clean_path = self._validate_safe_path(path)"""
    old_supa_read = """    def read_file(self, path: str) -> bytes:
        clean_path = path.lstrip("/")"""
    new_supa_read = """    def read_file(self, path: str) -> bytes:
        clean_path = self._validate_safe_path(path)"""
    old_supa_del = """    def delete_file(self, path: str) -> None:
        clean_path = path.lstrip("/")"""
    new_supa_del = """    def delete_file(self, path: str) -> None:
        clean_path = self._validate_safe_path(path)"""
    patch_file(p_supa_storage, [
        (old_supa_init, new_supa_init),
        (old_supa_save, new_supa_save),
        (old_supa_read, new_supa_read),
        (old_supa_del, new_supa_del),
    ])

    # ------------------------------------------------------------------------
    # 4. app/dependencies.py: Enforce password change in require_role
    # ------------------------------------------------------------------------
    p_deps = BASE_DIR / "app" / "dependencies.py"
    old_require_role = """def require_role(*allowed_roles: str):
    \"\"\"
    FastAPI dependency enforcing JWT + role-based access control.

    Reads the 'Authorization: Bearer <token>' header, decodes the JWT, and
    extracts user_id / role. Raises 401 on invalid credentials and 403 when
    the authenticated role is not permitted.
    If no roles are passed, defaults to allowing any valid authenticated role.
    \"\"\"
    effective_roles = set(allowed_roles) if allowed_roles else VALID_ROLES

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

        if role not in effective_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this operation.")

        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "requires_password_change": bool(payload.get("requires_password_change")),
        }

    return _enforce"""
    new_require_role = """def require_role(*allowed_roles: str, allow_password_change_pending: bool = False):
    \"\"\"
    FastAPI dependency enforcing JWT + role-based access control.

    Reads the 'Authorization: Bearer <token>' header, decodes the JWT, and
    extracts user_id / role. Raises 401 on invalid credentials and 403 when
    the authenticated role is not permitted.
    If no roles are passed, defaults to allowing any valid authenticated role.
    \"\"\"
    effective_roles = set(allowed_roles) if allowed_roles else VALID_ROLES

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

        if role not in effective_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this operation.")

        requires_pwd = bool(payload.get("requires_password_change"))
        if requires_pwd and not allow_password_change_pending:
            raise HTTPException(
                status_code=403,
                detail="Password change required before accessing this resource."
            )

        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "requires_password_change": requires_pwd,
        }

    return _enforce"""
    patch_file(p_deps, [(old_require_role, new_require_role)])

    # ------------------------------------------------------------------------
    # 5. app/routers/auth.py: Allow password change endpoint to pass through
    # ------------------------------------------------------------------------
    p_auth = BASE_DIR / "app" / "routers" / "auth.py"
    old_auth_me = """@router.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(require_role())):"""
    new_auth_me = """@router.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(require_role(allow_password_change_pending=True))):"""
    old_auth_change = """@router.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(require_role()),
):"""
    new_auth_change = """@router.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(require_role(allow_password_change_pending=True)),
):"""
    patch_file(p_auth, [
        (old_auth_me, new_auth_me),
        (old_auth_change, new_auth_change),
    ])

    # ------------------------------------------------------------------------
    # 6. app/routers/compare.py: Semantic calibration & async executor
    # ------------------------------------------------------------------------
    p_compare = BASE_DIR / "app" / "routers" / "compare.py"
    old_compare_decompress = """                    if row:
                        from plagiarism_engine.db.helpers import decompress_text
                        raw_c = row[0]
                        content_str = decompress_text(raw_c) if isinstance(raw_c, (bytes, bytearray, memoryview)) else (raw_c or "")
                        return content_str, row[1] or file_type_for(file_path) or "text", f"{project_id} : {file_path}\""""
    new_compare_decompress = """                    if row:
                        from plagiarism_engine.db.helpers import decompress_text
                        raw_c = row[0]
                        content_str = decompress_text(raw_c)
                        return content_str, row[1] or file_type_for(file_path) or "text", f"{project_id} : {file_path}\""""

    old_compare_semantic = """    # Calculate semantic embedding similarity between the two documents
    semantic_score = 0.0
    try:
        import numpy as np
        from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
        from plagiarism_engine.vectors.pgvector_store import PgVectorStore
        from plagiarism_engine.text_detector import normalize_arabic_text

        domain_key = DOMAIN_MODEL_KEYS.get(eff_type, "bge_m3")
        model, _ = model_pool.get_model_with_name(domain_key)
        if model is not None:
            text_a = normalize_arabic_text(content_a[:2500]) if eff_type == "text" else content_a[:2500]
            text_b = normalize_arabic_text(content_b[:2500]) if eff_type == "text" else content_b[:2500]
            emb_a = model.encode(text_a, convert_to_numpy=True)
            emb_b = model.encode(text_b, convert_to_numpy=True)
            vec_a = PgVectorStore._normalize_and_pad_1d(emb_a, 1024)
            vec_b = PgVectorStore._normalize_and_pad_1d(emb_b, 1024)
            raw_cosine = float(np.dot(vec_a, vec_b))
            semantic_score = float(max(0.0, min(1.0, raw_cosine)))
    except Exception as e:
        print(f"Warning computing direct file comparison semantic score: {e}")"""
    new_compare_semantic = """    # Calculate semantic embedding similarity between the two documents
    semantic_score = 0.0
    try:
        import numpy as np
        from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
        from plagiarism_engine.vectors.pgvector_store import PgVectorStore
        from plagiarism_engine.text_detector import normalize_arabic_text
        from plagiarism_engine.fusion_scorer import calibrate_semantic

        domain_key = DOMAIN_MODEL_KEYS.get(eff_type, "bge_m3")
        model, model_name = model_pool.get_model_with_name(domain_key)
        if model is not None:
            text_a = normalize_arabic_text(content_a[:2500]) if eff_type == "text" else content_a[:2500]
            text_b = normalize_arabic_text(content_b[:2500]) if eff_type == "text" else content_b[:2500]
            loop = asyncio.get_running_loop()
            emb_a, emb_b = await loop.run_in_executor(
                None,
                lambda: (
                    model.encode(text_a, convert_to_numpy=True),
                    model.encode(text_b, convert_to_numpy=True),
                )
            )
            vec_a = PgVectorStore._normalize_and_pad_1d(emb_a, 1024)
            vec_b = PgVectorStore._normalize_and_pad_1d(emb_b, 1024)
            raw_cosine = float(np.dot(vec_a, vec_b))
            calibrated = calibrate_semantic(raw_cosine, model_name)
            semantic_score = float(max(0.0, min(1.0, calibrated)))
    except Exception as e:
        print(f"Warning computing direct file comparison semantic score: {e}")"""
    patch_file(p_compare, [
        (old_compare_decompress, new_compare_decompress),
        (old_compare_semantic, new_compare_semantic),
    ])

    # ------------------------------------------------------------------------
    # 7. app/services/intake.py: Pairwise semantic fallback & stale FP purge
    # ------------------------------------------------------------------------
    p_intake = BASE_DIR / "app" / "services" / "intake.py"
    old_intake_sem = """                # Get the pre-calculated Semantic Score from pgvector (fast O(1) lookup)
                sem_key = (rel_path, other_pid, other_path)
                precalc_semantic_score = semantic_lookup.get(sem_key, 0.0)"""
    new_intake_sem = """                # Get the pre-calculated Semantic Score from pgvector (fast O(1) lookup)
                sem_key = (rel_path, other_pid, other_path)
                if sem_key in semantic_lookup:
                    precalc_semantic_score = semantic_lookup[sem_key]
                elif hasattr(vstore, "get_pair_similarity"):
                    precalc_semantic_score = vstore.get_pair_similarity(project_name, rel_path, other_pid, other_path)
                    semantic_lookup[sem_key] = precalc_semantic_score
                else:
                    precalc_semantic_score = 0.0"""
    old_intake_fp = """    log("💾 Storing new fingerprints to database index (batch mode)...")
    batch = []
    for f in project_files:
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if fps:
            batch.append((rel_path, ftype, fps))
    db.store_fingerprints_batch(project_name, batch)"""
    new_intake_fp = """    log("💾 Storing new fingerprints to database index (batch mode)...")
    # Clean stale fingerprints for project if re-uploading
    try:
        conn = db._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM fingerprint_index WHERE project_id = %s;", (project_name,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    batch = []
    for f in project_files:
        rel_path = f.get("relative_path", f.get("filename", ""))
        ftype = f.get("file_type", "")
        fps = file_fingerprints.get(rel_path, [])
        if fps:
            batch.append((rel_path, ftype, fps))
    db.store_fingerprints_batch(project_name, batch)"""
    patch_file(p_intake, [
        (old_intake_sem, new_intake_sem),
        (old_intake_fp, new_intake_fp),
    ])

    # ------------------------------------------------------------------------
    # 8. plagiarism_engine/db/projects_store.py: Re-upload orphan cleanup & nullify embeddings
    # ------------------------------------------------------------------------
    p_projects_store = BASE_DIR / "plagiarism_engine" / "db" / "projects_store.py"
    old_save_proj_sql = """            if self.mode == "postgresql":
                cur.execute("INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;", (pid, pname))
                if file_rows:
                    cur.executemany(\"\"\"
                        INSERT INTO project_files (id, project_id, relative_path, file_type, content)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET file_type=EXCLUDED.file_type;
                    \"\"\", file_rows)"""
    new_save_proj_sql = """            if self.mode == "postgresql":
                cur.execute("INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;", (pid, pname))
                if file_rows:
                    new_rel_paths = [r[2] for r in file_rows]
                    # Clean up deleted files from previous upload
                    cur.execute("DELETE FROM project_files WHERE project_id = %s AND relative_path != ALL(%s);", (pid, new_rel_paths))
                    cur.executemany(\"\"\"
                        INSERT INTO project_files (id, project_id, relative_path, file_type, content)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET file_type=EXCLUDED.file_type, embedding_binary=NULL, embedding=NULL;
                    \"\"\", file_rows)"""
    patch_file(p_projects_store, [(old_save_proj_sql, new_save_proj_sql)])

    # ------------------------------------------------------------------------
    # 9. plagiarism_engine/db/teams_store.py: Real member count in get_all_teams
    # ------------------------------------------------------------------------
    p_teams_store = BASE_DIR / "plagiarism_engine" / "db" / "teams_store.py"
    old_teams_sql = """            if college_id:
                cid = clean_str(college_id)
                if self.mode == "postgresql":
                    cur.execute("SELECT id, name, college_id, created_at, COALESCE(submission_allowed, FALSE) FROM teams WHERE college_id = %s ORDER BY created_at DESC;", (cid,))
                else:
                    cur.execute("SELECT id, name, college_id, created_at, COALESCE(submission_allowed, 0) FROM teams WHERE college_id = ? ORDER BY created_at DESC;", (cid,))
            else:
                cur.execute("SELECT id, name, college_id, created_at, COALESCE(submission_allowed, FALSE) FROM teams ORDER BY created_at DESC;")
            rows = cur.fetchall()

            teams = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    d = dict(r)
                    d["submission_allowed"] = bool(d.get("submission_allowed", False))
                    teams.append(d)
                else:
                    teams.append({
                        "id": r[0],
                        "name": r[1],
                        "college_id": r[2],
                        "created_at": r[3],
                        "submission_allowed": bool(r[4]) if len(r) > 4 else False,
                    })"""
    new_teams_sql = """            if college_id:
                cid = clean_str(college_id)
                if self.mode == "postgresql":
                    cur.execute(\"\"\"
                        SELECT t.id, t.name, t.college_id, t.created_at, COALESCE(t.submission_allowed, FALSE), COUNT(s.id) AS member_count
                        FROM teams t
                        LEFT JOIN students s ON s.team_id = t.id
                        WHERE t.college_id = %s
                        GROUP BY t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                        ORDER BY t.created_at DESC;
                    \"\"\", (cid,))
                else:
                    cur.execute(\"\"\"
                        SELECT t.id, t.name, t.college_id, t.created_at, COALESCE(t.submission_allowed, 0), COUNT(s.id) AS member_count
                        FROM teams t
                        LEFT JOIN students s ON s.team_id = t.id
                        WHERE t.college_id = ?
                        GROUP BY t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                        ORDER BY t.created_at DESC;
                    \"\"\", (cid,))
            else:
                if self.mode == "postgresql":
                    cur.execute(\"\"\"
                        SELECT t.id, t.name, t.college_id, t.created_at, COALESCE(t.submission_allowed, FALSE), COUNT(s.id) AS member_count
                        FROM teams t
                        LEFT JOIN students s ON s.team_id = t.id
                        GROUP BY t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                        ORDER BY t.created_at DESC;
                    \"\"\")
                else:
                    cur.execute(\"\"\"
                        SELECT t.id, t.name, t.college_id, t.created_at, COALESCE(t.submission_allowed, 0), COUNT(s.id) AS member_count
                        FROM teams t
                        LEFT JOIN students s ON s.team_id = t.id
                        GROUP BY t.id, t.name, t.college_id, t.created_at, t.submission_allowed
                        ORDER BY t.created_at DESC;
                    \"\"\")
            rows = cur.fetchall()

            teams = []
            for r in rows:
                if isinstance(r, dict) or hasattr(r, 'keys'):
                    d = dict(r)
                    d["submission_allowed"] = bool(d.get("submission_allowed", False))
                    d["member_count"] = int(d.get("member_count") or 0)
                    teams.append(d)
                else:
                    teams.append({
                        "id": r[0],
                        "name": r[1],
                        "college_id": r[2],
                        "created_at": r[3],
                        "submission_allowed": bool(r[4]) if len(r) > 4 else False,
                        "member_count": int(r[5]) if len(r) > 5 else 0,
                    })"""
    patch_file(p_teams_store, [(old_teams_sql, new_teams_sql)])

    # ------------------------------------------------------------------------
    # 10. app/state.py: Preload only unixcoder & bge_m3
    # ------------------------------------------------------------------------
    p_state = BASE_DIR / "app" / "state.py"
    old_preload = """def _preload_models():
    \"\"\"Background preload of ML models so first scan is fast.\"\"\"
    global _models_ready
    try:
        from plagiarism_engine.vector_store import model_pool
        model_pool.get_model("code")
        model_pool.get_model("bge_m3")
        model_pool.get_model("minilm")
        _models_ready = True
    except Exception as e:
        print(f"Failed to preload models: {e}")"""
    new_preload = """def _preload_models():
    \"\"\"Background preload of ML models actually used (UniXcoder & BGE-M3).\"\"\"
    global _models_ready
    try:
        from plagiarism_engine.vector_store import model_pool
        model_pool.get_model("unixcoder")
        model_pool.get_model("bge_m3")
        _models_ready = True
    except Exception as e:
        print(f"Failed to preload models: {e}")"""
    patch_file(p_state, [(old_preload, new_preload)])

    # ------------------------------------------------------------------------
    # 11. app/routers/dashboard.py: History ordering
    # ------------------------------------------------------------------------
    p_dash = BASE_DIR / "app" / "routers" / "dashboard.py"
    old_dash_hist = """        history = _load_history()
        recent_scans = history[::-1][:10] if history else []"""
    new_dash_hist = """        history = _load_history()
        recent_scans = history[:10] if history else []"""
    patch_file(p_dash, [(old_dash_hist, new_dash_hist)])

    # ------------------------------------------------------------------------
    # 12. app/services/git_clone.py: Hardening symlinks, prompt, SSRF
    # ------------------------------------------------------------------------
    p_git = BASE_DIR / "app" / "services" / "git_clone.py"
    old_git_clone = """    # Skip Git LFS (Large File Storage) objects to speed up clones
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
        )"""
    new_git_clone = """    # Block SSRF: ensure host is not loopback, link-local, or private RFC1918
    from urllib.parse import urlparse
    import ipaddress
    parsed_url = urlparse(repo_url)
    hostname = (parsed_url.hostname or "").lower()
    if not hostname or hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"}:
        raise HTTPException(status_code=400, detail="Cloning from localhost or private network is forbidden")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise HTTPException(status_code=400, detail="Cloning from private/loopback IP is forbidden")
    except ValueError:
        pass

    # Skip Git LFS and disable prompts/symlinks
    env = os.environ.copy()
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        subprocess.run(
            ["git", "-c", "core.symlinks=false", "clone", "--depth", "1", "--branch", branch, "--", clone_url, tmp_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )"""
    patch_file(p_git, [(old_git_clone, new_git_clone)])

    print("\\nBackend patches applied successfully!")

if __name__ == "__main__":
    main()
