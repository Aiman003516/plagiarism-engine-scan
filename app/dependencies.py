"""JWT configuration, token creation and the require_role() RBAC dependency."""

import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError


from plagiarism_engine.config import load_project_env

load_project_env()

# ============================================================================
# AUTHENTICATION & RBAC (JWT)
# ============================================================================

from typing import Optional

KNOWN_JWT_PLACEHOLDERS = {
    "your-secret-here",
    "change-me",
    "changeme",
    "secret",
    "secret-key",
    "secretkey",
    "jwt-secret",
    "default-secret",
    "password",
    "admin",
    "12345678",
}


def validate_jwt_secret(secret: Optional[str] = None, app_env: Optional[str] = None) -> str:
    """Validate JWT_SECRET. In production, refuse empty, known placeholder, or <32 char secrets."""
    env = (app_env if app_env is not None else os.environ.get("APP_ENV", "")).strip().lower()
    is_prod = env == "production"

    if is_prod:
        if not secret or not str(secret).strip():
            raise RuntimeError(
                "JWT_SECRET must be set when APP_ENV=production. "
                "Add a long random JWT_SECRET to the environment or .env file."
            )
        s = str(secret).strip()
        if s.lower() in KNOWN_JWT_PLACEHOLDERS:
            raise RuntimeError(
                f"JWT_SECRET cannot be a known insecure placeholder ('{s}') when APP_ENV=production."
            )
        if len(s) < 32:
            raise RuntimeError(
                f"JWT_SECRET must be at least 32 characters long when APP_ENV=production (got {len(s)} chars)."
            )
        return s

    # Development or testing fallback
    if secret and str(secret).strip():
        return str(secret).strip()

    import secrets as _secrets
    import warnings
    generated = _secrets.token_hex(32)
    warnings.warn(
        "JWT_SECRET not set in environment. Generated a random secret. "
        "All tokens will be invalidated on server restart. "
        "Set JWT_SECRET in your .env file for production.",
        stacklevel=2,
    )
    return generated


JWT_SECRET = validate_jwt_secret(os.environ.get("JWT_SECRET"), os.environ.get("APP_ENV"))
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

VALID_ROLES = {"ministry_admin", "university_admin", "college_admin", "faculty", "student"}
STAFF_ROLES = {"ministry_admin", "university_admin", "college_admin", "faculty"}
ADMIN_ROLES = {"ministry_admin", "university_admin", "college_admin"}

def require_role(*allowed_roles: str, allow_password_change_pending: bool = False):
    """
    FastAPI dependency enforcing JWT + role-based access control.

    Reads the 'Authorization: Bearer <token>' header, decodes the JWT, and
    extracts user_id / role. Raises 401 on invalid credentials and 403 when
    the authenticated role is not permitted.
    If no roles are passed, defaults to allowing any valid authenticated role.
    """
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

    return _enforce
