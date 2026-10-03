"""JWT configuration, token creation and the require_role() RBAC dependency."""

import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError


# ============================================================================
# AUTHENTICATION & RBAC (JWT)
# ============================================================================

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    import secrets as _secrets
    JWT_SECRET = _secrets.token_hex(32)
    import warnings
    warnings.warn(
        "JWT_SECRET not set in environment. Generated a random secret. "
        "All tokens will be invalidated on server restart. "
        "Set JWT_SECRET in your .env file for production.",
        stacklevel=2,
    )
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
