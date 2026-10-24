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
    university_id: Optional[str] = None
    college_id: Optional[str] = None
    department_id: Optional[str] = None
    department: Optional[str] = None
    university: Optional[str] = None


class StudentBulkImportItem(BaseModel):
    name: str
    enrollment_number: str
    university_id: Optional[str] = None
    college_id: Optional[str] = None
    department_id: Optional[str] = None
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
    university_id: Optional[str] = None
    college_id: Optional[str] = None
    department_id: Optional[str] = None
    requires_password_change: Optional[bool] = None


def _serialize_user(user: dict) -> dict:
    """Strip password_hash from user responses."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "university_id": user.get("university_id"),
        "college_id": user.get("college_id"),
        "department_id": user.get("department_id"),
        "requires_password_change": bool(user.get("requires_password_change")),
        "created_at": user.get("created_at"),
    }


@router.get("/api/users")
async def list_users(
    role: Optional[str] = None,
    college_id: Optional[str] = None,
    university_id: Optional[str] = None,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    db = get_db()
    loop = asyncio.get_running_loop()
    users = await loop.run_in_executor(None, lambda: db.get_all_users(role_filter=role))

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    if caller_role == "college_admin":
        caller_college = caller_record.get("college_id")
        users = [
            u for u in users
            if (u.get("college_id") == caller_college or u.get("id") == current_user["user_id"])
            and u.get("role") in ("faculty", "student", "college_admin")
        ]
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        users = [
            u for u in users
            if u.get("university_id") == caller_uni
            and u.get("role") != "ministry_admin"
        ]
    else:
        # ministry_admin can view all users, filtered optionally by query params
        if college_id is not None:
            users = [u for u in users if u.get("college_id") == college_id]
        if university_id is not None:
            users = [u for u in users if u.get("university_id") == university_id]

    return {"users": [_serialize_user(u) for u in users]}


@router.post("/api/users")
async def create_user_endpoint(
    payload: UserCreate,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    db = get_db()
    loop = asyncio.get_running_loop()
    name = payload.name.strip()

    valid_roles = {"ministry_admin", "university_admin", "college_admin", "faculty", "student"}
    if payload.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    # Enforce delegation hierarchy
    if caller_role == "college_admin":
        if payload.role not in ("faculty", "student"):
            raise HTTPException(
                status_code=403,
                detail="College administrators can only create faculty and student accounts."
            )
        caller_college = caller_record.get("college_id")
        if payload.college_id and caller_college and payload.college_id != caller_college:
            raise HTTPException(
                status_code=403,
                detail="College administrators cannot create users for a different college."
            )
        payload.college_id = caller_college
        payload.university_id = caller_record.get("university_id")
    elif caller_role == "university_admin":
        if payload.role in ("ministry_admin", "university_admin"):
            raise HTTPException(
                status_code=403,
                detail="University administrators cannot assign roles at or above their level."
            )
        caller_uni = caller_record.get("university_id")
        if payload.university_id and caller_uni and payload.university_id != caller_uni:
            raise HTTPException(
                status_code=403,
                detail="University administrators cannot create users for a different university."
            )
        payload.university_id = caller_uni

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
            if payload.university_id or payload.department_id:
                db.update_user(user_id, university_id=payload.university_id, department_id=payload.department_id)
            return "OK", db.get_user_by_id(user_id)
        else:
            db.create_user(user_id, name, email, password_hash, payload.role, payload.college_id)
            if payload.university_id or payload.department_id:
                db.update_user(user_id, university_id=payload.university_id, department_id=payload.department_id)
            return "OK", db.get_user_by_id(user_id)

    status, user = await loop.run_in_executor(None, _precheck_and_create)
    if status == "ADMIN_SELF_LOCK":
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    if status == "EMAIL_REGISTERED":
        raise HTTPException(status_code=400, detail="Email already registered")
    if status == "STUDENT_REGISTERED":
        raise HTTPException(status_code=400, detail="Student with this enrollment number already exists")

    return _serialize_user(user)


@router.post("/api/users/bulk-import-students")
async def bulk_import_students(
    payload: StudentBulkImportPayload,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    """Batch import students from parsed CSV or Excel payload."""
    db = get_db()
    loop = asyncio.get_running_loop()
    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    def _batch_import():
        imported = 0
        skipped = 0
        errors = []
        for s in payload.students:
            enum = s.enrollment_number.strip()
            name = s.name.strip()
            if not enum or not name:
                errors.append("Row skipped: missing name or enrollment number")
                continue
            if db.get_student_by_enrollment_number(enum):
                skipped += 1
                continue
            pwd = s.password or "123456"
            pwd_hash = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            uid = str(uuid.uuid4())
            effective_college = caller_record.get("college_id") if caller_role == "college_admin" else (s.college_id or caller_record.get("college_id"))
            effective_uni = caller_record.get("university_id") if caller_role in ("college_admin", "university_admin") else (s.university_id or caller_record.get("university_id"))
            try:
                db.create_student(
                    id=uid,
                    enrollment_number=enum,
                    name=name,
                    password_hash=pwd_hash,
                    requires_password_change=True,
                )
                db.create_user(uid, name, enum, pwd_hash, "student", effective_college)
                if effective_uni or s.department_id:
                    db.update_user(uid, university_id=effective_uni, department_id=s.department_id)
                imported += 1
            except Exception as e:
                errors.append(f"Error importing {enum}: {str(e)}")
        return imported, skipped, errors

    imported, skipped, errors = await loop.run_in_executor(None, _batch_import)
    return {"imported": imported, "skipped": skipped, "errors": errors}


@router.get("/api/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    db = get_db()
    loop = asyncio.get_running_loop()
    user = await loop.run_in_executor(None, lambda: db.get_user_by_id(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}
    if caller_role == "college_admin":
        caller_college = caller_record.get("college_id")
        if user.get("college_id") != caller_college and user.get("id") != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Insufficient permissions to view a user from another college.")
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        if user.get("university_id") and caller_uni and user.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Insufficient permissions to view a user from another university.")

    return _serialize_user(user)


@router.put("/api/users/{user_id}")
async def update_user_endpoint(
    user_id: str,
    payload: UserUpdate,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    db = get_db()
    loop = asyncio.get_running_loop()

    # --- Admin Self-Lock validation --------------------------------------
    if payload.role is not None and current_user["user_id"] == user_id and current_user["role"] != payload.role:
        raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
    if payload.role is not None:
        valid_roles = {"ministry_admin", "university_admin", "college_admin", "faculty", "student"}
        if payload.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")

    existing = await loop.run_in_executor(None, lambda: db.get_user_by_id(user_id))
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    # --- Last Ministry Admin Guard ---------------------------------------
    if existing.get("role") == "ministry_admin" and payload.role is not None and payload.role != "ministry_admin":
        all_users = await loop.run_in_executor(None, lambda: db.get_all_users())
        min_admins = [u for u in all_users if u.get("role") == "ministry_admin"]
        if len(min_admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active ministry administrator.")

    # --- Scope & Role Delegation Guards ----------------------------------
    if caller_role == "college_admin":
        caller_college = caller_record.get("college_id")
        if existing.get("college_id") != caller_college and current_user["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Insufficient permissions to modify a user from another college.")
        if current_user["user_id"] != user_id and existing.get("role") in ("ministry_admin", "university_admin", "college_admin"):
            raise HTTPException(status_code=403, detail="College administrators cannot modify administrative accounts.")
        if payload.role is not None and payload.role not in ("faculty", "student"):
            raise HTTPException(status_code=403, detail="College administrators can only assign faculty or student roles.")

    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        if existing.get("university_id") and caller_uni and existing.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Insufficient permissions to modify a user from another university.")
        if current_user["user_id"] != user_id and existing.get("role") in ("ministry_admin", "university_admin"):
            raise HTTPException(status_code=403, detail="University administrators cannot modify ministry or university administrator accounts.")
        if payload.role is not None and payload.role in ("ministry_admin", "university_admin"):
            raise HTTPException(status_code=403, detail="University administrators cannot promote users to ministry or university administrator.")

    def _update():
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
        if payload.university_id is not None:
            fields["university_id"] = payload.university_id
        if payload.department_id is not None:
            fields["department_id"] = payload.department_id
        if payload.requires_password_change is not None:
            fields["requires_password_change"] = payload.requires_password_change

        if fields:
            db.update_user(user_id, **fields)

        return "OK", db.get_user_by_id(user_id)

    status, user = await loop.run_in_executor(None, _update)
    if status == "EMAIL_REGISTERED":
        raise HTTPException(status_code=400, detail="Email already registered")

    return _serialize_user(user)


@router.delete("/api/users/{user_id}")
async def delete_user_endpoint(
    user_id: str,
    current_user: dict = Depends(require_role("ministry_admin", "university_admin", "college_admin")),
):
    # --- Self Deletion Guard ---------------------------------------------
    if current_user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Admins cannot delete their own account.")

    db = get_db()
    loop = asyncio.get_running_loop()
    existing = await loop.run_in_executor(None, lambda: db.get_user_by_id(user_id))
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # --- Last Ministry Admin Guard ---------------------------------------
    if existing.get("role") == "ministry_admin":
        all_users = await loop.run_in_executor(None, lambda: db.get_all_users())
        min_admins = [u for u in all_users if u.get("role") == "ministry_admin"]
        if len(min_admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last active ministry administrator.")

    caller_role = current_user.get("role")
    caller_record = await loop.run_in_executor(None, lambda: db.get_user_by_id(current_user["user_id"])) or {}

    # --- Scope Guards ----------------------------------------------------
    if caller_role == "college_admin":
        caller_college = caller_record.get("college_id")
        if existing.get("college_id") != caller_college:
            raise HTTPException(status_code=403, detail="Insufficient permissions to delete a user from another college.")
        if existing.get("role") in ("ministry_admin", "university_admin", "college_admin"):
            raise HTTPException(status_code=403, detail="College administrators cannot delete administrator accounts.")
    elif caller_role == "university_admin":
        caller_uni = caller_record.get("university_id")
        if existing.get("university_id") and caller_uni and existing.get("university_id") != caller_uni:
            raise HTTPException(status_code=403, detail="Insufficient permissions to delete a user from another university.")
        if existing.get("role") in ("ministry_admin", "university_admin"):
            raise HTTPException(status_code=403, detail="University administrators cannot delete ministry or university administrator accounts.")

    await loop.run_in_executor(None, lambda: db.delete_user(user_id))
    return {"detail": "User deleted"}
