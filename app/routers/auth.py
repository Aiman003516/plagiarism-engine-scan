"""Authentication endpoints: login, current user, change password."""

from typing import Optional
from fastapi import HTTPException, Depends
from pydantic import BaseModel
import bcrypt


from fastapi import APIRouter
from app.dependencies import _create_access_token, require_role
from app.state import get_db

router = APIRouter(tags=["auth"])


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

def _enrich_user_institutions(db, user: dict) -> dict:
    """Enrich user or student dict with institutional human-readable names."""
    enriched = dict(user)
    conn = db._get_connection()
    try:
        cur = conn.cursor()
        uni_id = enriched.get("university_id")
        col_id = enriched.get("college_id")
        dept_id = enriched.get("department_id")

        if uni_id:
            cur.execute("SELECT name FROM universities WHERE id = %s;", (uni_id,))
            r = cur.fetchone()
            enriched["university_name"] = r[0] if r else None
        else:
            enriched["university_name"] = None

        if col_id:
            cur.execute("SELECT name FROM colleges WHERE id = %s;", (col_id,))
            r = cur.fetchone()
            enriched["college_name"] = r[0] if r else None
        else:
            enriched["college_name"] = None

        if dept_id:
            cur.execute("SELECT name FROM departments WHERE id = %s;", (dept_id,))
            r = cur.fetchone()
            enriched["department_name"] = r[0] if r else None
        else:
            enriched["department_name"] = None
    except Exception:
        pass
    finally:
        conn.close()
    return enriched


@router.post("/api/auth/login")
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

    enriched = _enrich_user_institutions(db, user)

    response_user = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "university_id": enriched.get("university_id"),
        "university_name": enriched.get("university_name"),
        "college_id": enriched.get("college_id"),
        "college_name": enriched.get("college_name"),
        "department_id": enriched.get("department_id"),
        "department_name": enriched.get("department_name"),
        "requires_password_change": requires_password_change,
    }
    if is_student:
        response_user["enrollment_number"] = user.get("enrollment_number")
        response_user["team_id"] = user.get("team_id")

    return {"token": token, "user": response_user}


@router.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(require_role(allow_password_change_pending=True))):
    db = get_db()
    user = db.get_user_by_id(current_user["user_id"])
    if user:
        enriched = _enrich_user_institutions(db, user)
        return {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "university_id": enriched.get("university_id"),
            "university_name": enriched.get("university_name"),
            "college_id": enriched.get("college_id"),
            "college_name": enriched.get("college_name"),
            "department_id": enriched.get("department_id"),
            "department_name": enriched.get("department_name"),
            "requires_password_change": bool(user.get("requires_password_change")),
            "created_at": user.get("created_at"),
        }

    # Student tokens resolve against the students table instead.
    student = db.get_student_by_id(current_user["user_id"])
    if not student:
        raise HTTPException(status_code=404, detail="User not found")

    enriched = _enrich_user_institutions(db, student)
    return {
        "id": student["id"],
        "name": student["name"],
        "email": student.get("enrollment_number"),
        "enrollment_number": student.get("enrollment_number"),
        "role": "student",
        "university_id": enriched.get("university_id"),
        "university_name": enriched.get("university_name"),
        "college_id": enriched.get("college_id"),
        "college_name": enriched.get("college_name"),
        "department_id": enriched.get("department_id"),
        "department_name": enriched.get("department_name"),
        "team_id": student.get("team_id"),
        "requires_password_change": bool(student.get("requires_password_change")),
        "created_at": student.get("created_at"),
    }


@router.post("/api/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(require_role(allow_password_change_pending=True)),
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
