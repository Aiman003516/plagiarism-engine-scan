"""Users CRUD endpoints."""

import uuid
from typing import Dict, Any, Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel
import bcrypt


from fastapi import APIRouter
from app.dependencies import require_role
from app.state import get_db

router = APIRouter(tags=["users"])


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


@router.get("/api/users", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def list_users(role: Optional[str] = None, college_id: Optional[str] = None):
    db = get_db()
    users = db.get_all_users(role_filter=role)
    if college_id is not None:
        users = [u for u in users if u.get("college_id") == college_id]
    return {"users": [_serialize_user(u) for u in users]}


@router.post("/api/users")
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

    valid_roles = {"ministry_admin", "college_admin", "faculty", "student"}
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


@router.get("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def get_user(user_id: str):
    db = get_db()
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@router.put("/api/users/{user_id}")
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
        valid_roles = {"ministry_admin", "college_admin", "faculty", "student"}
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


@router.delete("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def delete_user_endpoint(user_id: str):
    db = get_db()
    existing = db.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete_user(user_id)
    return {"detail": "User deleted"}
