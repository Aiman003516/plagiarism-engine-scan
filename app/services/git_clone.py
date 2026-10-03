"""Git repository cloning with credential scrubbing."""

import os
import re
import shutil
import tempfile
import subprocess
from typing import Optional
from fastapi import HTTPException


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
        sanitized = re.sub(r'oauth2:[^@]+@', 'oauth2:****@', e.stderr or "")
        sanitized = re.sub(r'://[^:]+:[^@]+@', '://****:****@', sanitized)
        raise HTTPException(status_code=400, detail=f"Git clone failed: {sanitized}")
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
