"""Users CRUD endpoints."""

import asyncio
import uuid
from typing import Dict, Any, Optional, List
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
    email: Optional[str] = None
    enrollment_number: Optional[str] = None
    password: Optional[str] = None
    role: str
    college_id: Optional[str] = None
    department: Optional[str] = None
    university: Optional[str] = None


class StudentBulkImportItem(BaseModel):
    name: str
    enrollment_number: str
    college_id: Optional[str] = None
    department: Optional[str] = None
    university: Optional[str] = None
    password: Optional[str] = None


class StudentBulkImportPayload(BaseModel):
    students: List[StudentBulkImportItem]


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
    loop = asyncio.get_running_loop()
    users = await loop.run_in_executor(None, lambda: db.get_all_users(role_filter=role))
    if college_id is not None:
        users = [u for u in users if u.get("college_id") == college_id]
    return {"users": [_serialize_user(u) for u in users]}


@router.post("/api/users")
async def create_user_endpoint(
    payload: UserCreate,
    current_user: dict = Depends(require_role("ministry_admin", "college_admin")),
):
    db = get_db()
    loop = asyncio.get_running_loop()
    name = payload.name.strip()

    valid_roles = {"ministry_admin", "college_admin", "faculty", "student"}
    if payload.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")

    # Determine identifier (email or enrollment number for student)
    if payload.role == "student":
        enum = (payload.enrollment_number or "").strip()
        if not enum:
            raise HTTPException(status_code=400, detail="Enrollment number is required for students.")
        email = (payload.email or f"{enum}@student.system").strip().lower()
        password = payload.password or "123456"
    else:
        email = (payload.email or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required.")
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password is required.")
        password = payload.password

    user_id = str(uuid.uuid4())

    def _precheck_and_create():
        # --- Admin Self-Lock -------------------------------------------------
        if current_user["user_id"] == user_id and current_user["role"] != payload.role:
            return "ADMIN_SELF_LOCK", None

        self_record = db.get_user_by_id(current_user["user_id"])
        if self_record and self_record.get("email") == email and current_user["role"] != payload.role:
            return "ADMIN_SELF_LOCK", None
        # ---------------------------------------------------------------------

        if db.get_user_by_email(email):
            return "EMAIL_REGISTERED", None

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        if payload.role == "student":
            senum = (payload.enrollment_number or "").strip()
            if db.get_student_by_enrollment_number(senum):
                return "STUDENT_REGISTERED", None
            # Insert into students table for team management
            db.create_student(
                id=user_id,
                enrollment_number=senum,
                name=name,
                password_hash=password_hash,
                requires_password_change=True,
            )
            # Also sync into users table so student can authenticate
            db.create_user(user_id, name, senum, password_hash, "student", payload.college_id)
            return "OK", db.get_user_by_id(user_id)
        else:
            db.create_user(user_id, name, email, password_hash, payload.role, payload.college_id)
            return "OK", db.get_user_by_id(user_id)

    status, user = await loop.run_in_executor(None, _precheck_and_create)
    if status == "ADMIN_SELF_LOCK":
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    if status == "EMAIL_REGISTERED":
        raise HTTPException(status_code=400, detail="Email already registered")
    if status == "STUDENT_REGISTERED":
        raise HTTPException(status_code=400, detail="Student with this enrollment number already exists")

    return _serialize_user(user)


@router.post("/api/users/bulk-import-students", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def bulk_import_students(payload: StudentBulkImportPayload):
    """Batch import students from parsed CSV or Excel payload."""
    db = get_db()
    loop = asyncio.get_running_loop()

    def _batch_import():
        imported = 0
        skipped = 0
        errors = []
        for s in payload.students:
            enum = s.enrollment_number.strip()
            name = s.name.strip()
            if not enum or not name:
                errors.append(f"Row skipped: missing name or enrollment number")
                continue
            if db.get_student_by_enrollment_number(enum):
                skipped += 1
                continue
            pwd = s.password or "123456"
            pwd_hash = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            uid = str(uuid.uuid4())
            try:
                db.create_student(
                    id=uid,
                    enrollment_number=enum,
                    name=name,
                    password_hash=pwd_hash,
                    requires_password_change=True,
                )
                db.create_user(uid, name, enum, pwd_hash, "student", s.college_id)
                imported += 1
            except Exception as e:
                errors.append(f"Error importing {enum}: {str(e)}")
        return imported, skipped, errors

    imported, skipped, errors = await loop.run_in_executor(None, _batch_import)
    return {"imported": imported, "skipped": skipped, "errors": errors}


@router.get("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def get_user(user_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()
    user = await loop.run_in_executor(None, lambda: db.get_user_by_id(user_id))
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
    loop = asyncio.get_running_loop()

    # --- Admin Self-Lock validation before heavy work --------------------
    if payload.role is not None and current_user["user_id"] == user_id and current_user["role"] != payload.role:
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    if payload.role is not None:
        valid_roles = {"ministry_admin", "college_admin", "faculty", "student"}
        if payload.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")
    # ---------------------------------------------------------------------

    def _update():
        existing = db.get_user_by_id(user_id)
        if not existing:
            return "NOT_FOUND", None

        if payload.email is not None:
            email = payload.email.strip().lower()
            other = db.get_user_by_email(email)
            if other and other["id"] != user_id:
                return "EMAIL_REGISTERED", None

        fields: Dict[str, Any] = {}
        if payload.name is not None:
            fields["name"] = payload.name.strip()
        if payload.email is not None:
            fields["email"] = payload.email.strip().lower()
        if payload.password is not None:
            fields["password_hash"] = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if payload.role is not None:
            fields["role"] = payload.role
        if payload.college_id is not None:
            fields["college_id"] = payload.college_id
        if payload.requires_password_change is not None:
            fields["requires_password_change"] = payload.requires_password_change

        if fields:
            db.update_user(user_id, **fields)

        return "OK", db.get_user_by_id(user_id)

    status, user = await loop.run_in_executor(None, _update)
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="User not found")
    if status == "EMAIL_REGISTERED":
        raise HTTPException(status_code=400, detail="Email already registered")

    return _serialize_user(user)


@router.delete("/api/users/{user_id}", dependencies=[Depends(require_role("ministry_admin", "college_admin"))])
async def delete_user_endpoint(user_id: str):
    db = get_db()
    loop = asyncio.get_running_loop()

    def _delete():
        existing = db.get_user_by_id(user_id)
        if not existing:
            return False
        db.delete_user(user_id)
        return True

    found = await loop.run_in_executor(None, _delete)
    if not found:
        raise HTTPException(status_code=404, detail="User not found")
    return {"detail": "User deleted"}
