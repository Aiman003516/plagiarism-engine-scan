# Autonomous System Investigation: RBAC Security, Database Schema Hierarchy, Permission Assignment, and Semantic Search

**Target System:** Plagiarism Detection Engine  
**Target Repository:** `C:\Users\Ayman\Downloads\plagiarism_engine_scan`  
**Auditor:** Principal Software Architect & Security Auditor  
**Audit Scope:** Clean-slate technical audit of database schema, UI routing & permission leaks, backend API endpoint authorization, role assignment governance, and semantic proposal search mechanics.

---

## Executive Summary

A comprehensive architectural and security audit was executed against the codebase and its live PostgreSQL database instance. The investigation reveals critical systemic flaws across all four architectural tiers:

1. **Entity Hierarchy Collapse**: Dedicated relational tables for `universities`, `colleges`, and `departments` **do not exist**. Institutional references are stored as unvalidated free-text strings or orphaned foreign keys. The `projects` table lacks a `college_id` column, while `users`, `students`, and `teams` lack `university` and `department` fields.
2. **Total UI Permission Leakage**: `frontend/src/Sidebar.tsx` renders all 7 administrative links to every user, including students. `frontend/src/App.tsx` contains a naive `ProtectedRoute` that only checks for token presence, with zero role verification. Students are redirected to `/dashboard` upon login and can freely navigate to `/scan`, `/`, `/users`, `/teams`, and `/settings`.
3. **Pervasive Backend Authorization Bypass**: The core dependency `require_role()` in `app/dependencies.py` has a logic flaw: when invoked without arguments (`require_role()`), it evaluates `if allowed_roles:` to `False` and skips role verification entirely. Consequently, **24 administrative and operational endpoints** across `compare.py`, `scanner.py`, `deep_scan.py`, `history.py`, `projects.py`, and `teams.py` are wide open to student execution, including scanner execution, git cloning, and audit report deletion. Furthermore, `GET /api/settings` has **no authentication whatsoever**.
4. **Role Assignment & Escalation Vulnerability**: `PUT /api/users/{user_id}` and `POST /api/users` allow a `college_admin` to create or promote any user to `ministry_admin` (Privilege Escalation). There are no scope boundaries enforcing university or college tenancy. In addition, `DELETE /api/users/{user_id}` lacks self-deletion protection, permitting an administrator to delete their own account and trigger self-lockout.
5. **Catastrophic Semantic Search Scalability Anti-Pattern**: In `POST /api/plagiarism/projects/semantic-search`, the engine bypasses PostgreSQL vector indexing entirely, pulls raw vectors over SQL as JSON strings, and calculates cosine similarities in Python memory. Most critically, lines 279–291 execute a live transformer neural network inference (`model.encode()`) on project abstracts **synchronously in a loop during every search request**, causing request latency to explode as project count scales. Furthermore, Arabic text normalization (`normalize_arabic`) is completely omitted.

---

## Task 1: Database Schema & Entity Hierarchy Audit

### 1.1 Live Database & Codebase Inspection Findings
- **Live Database Verified:** PostgreSQL 16 on `localhost:5432/plagiarism_engine_db`.
- **Files Inspected:**
  - [plagiarism_engine/db/schema.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/schema.py#L28-L154)
  - [plagiarism_engine/db/projects_store.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/projects_store.py#L117-L232)
  - [plagiarism_engine/db/users_store.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/users_store.py#L14-L106)
  - [plagiarism_engine/db/teams_store.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/teams_store.py#L14-L60)

```
========================================================================================
ENTITY EXISTENCE & COLUMN MAPPING TABLE
========================================================================================
Table Name      | Dedicated Table? | university col?     | college_id col?  | department col?
----------------|------------------|---------------------|------------------|-------------------
universities    | ❌ DOES NOT EXIST | N/A                 | N/A              | N/A
colleges        | ❌ DOES NOT EXIST | N/A                 | N/A              | N/A
departments     | ❌ DOES NOT EXIST | N/A                 | N/A              | N/A
projects        | ✅ Exists        | ✅ VARCHAR(255) (Str)| ❌ MISSING        | ✅ VARCHAR(255) (Str)
users           | ✅ Exists        | ❌ MISSING           | ✅ VARCHAR(255)   | ❌ MISSING
students        | ✅ Exists        | ❌ MISSING           | ✅ VARCHAR(255)   | ❌ MISSING
teams           | ✅ Exists        | ❌ MISSING           | ✅ VARCHAR(255)   | ❌ MISSING
project_files   | ✅ Exists        | N/A                 | N/A              | N/A
scan_reports    | ✅ Exists        | ❌ MISSING           | ❌ MISSING        | ❌ MISSING
========================================================================================
```

### 1.2 Identified Flaws & Orphaned Foreign Keys
1. **Lack of Entity Tables**: `universities`, `colleges`, and `departments` do not exist. Any user can type arbitrary text into `university` and `department` (e.g., `"Sana'a Univ"`, `"Sanaa University"`, `"جامعة صنعاء"`), leading to severe data fragmentation and impossible institutional filtering.
2. **Missing `college_id` on `projects`**: In `projects` ([schema.py:125-132](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/schema.py#L125-L132)), `university` and `department` exist as strings, but `college_id` is completely absent. A College Administrator cannot filter projects by college without brittle text heuristics.
3. **Missing `university` and `department` on `users`, `students`, and `teams`**: In `users` ([schema.py:86-95](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/schema.py#L86-L95)), `students` ([schema.py:96-105](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/schema.py#L96-L105)), and `teams` ([schema.py:109-114](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/db/schema.py#L109-L114)), only `college_id` exists. There is no `university_id` or `department_id`.
4. **Missing Relational Constraints**: The live database query confirms that only **one single foreign key exists across the entire database**: `project_files.project_id -> projects.id`. `students.team_id` has no foreign key to `teams.id`; `projects.team_id` has no foreign key to `teams.id`; and `college_id` columns point to non-existent tables.

---

### 1.3 Target 4-Tier Hierarchy Database Migration

To enforce the strict administrative hierarchy:
$$\text{Ministry Admin (Global)} \longrightarrow \text{University Admin} \longrightarrow \text{College Admin / Faculty} \longrightarrow \text{Student}$$

The following SQL migration must be executed:

```sql
-- ============================================================================
-- MIGRATION: 001_institutional_hierarchy_and_rbac.sql
-- ============================================================================

BEGIN;

-- 1. Create Dedicated Hierarchy Entity Tables
CREATE TABLE IF NOT EXISTS universities (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS colleges (
    id VARCHAR(64) PRIMARY KEY,
    university_id VARCHAR(64) NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_university_college_code UNIQUE(university_id, code)
);

CREATE TABLE IF NOT EXISTS departments (
    id VARCHAR(64) PRIMARY KEY,
    college_id VARCHAR(64) NOT NULL REFERENCES colleges(id) ON DELETE RESTRICT,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_college_dept_code UNIQUE(college_id, code)
);

-- 2. Clean up & Align Existing Relational Tables
-- Teams
ALTER TABLE teams 
    ADD COLUMN IF NOT EXISTS university_id VARCHAR(64) REFERENCES universities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS department_id VARCHAR(64) REFERENCES departments(id) ON DELETE RESTRICT;

-- Ensure college_id on teams references colleges
-- (After data migration of orphaned strings to UUIDs)
-- ALTER TABLE teams ADD CONSTRAINT fk_teams_college FOREIGN KEY (college_id) REFERENCES colleges(id) ON DELETE RESTRICT;

-- Students
ALTER TABLE students 
    ADD COLUMN IF NOT EXISTS university_id VARCHAR(64) REFERENCES universities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS department_id VARCHAR(64) REFERENCES departments(id) ON DELETE RESTRICT;

ALTER TABLE students
    DROP CONSTRAINT IF EXISTS fk_students_team,
    ADD CONSTRAINT fk_students_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

-- Users (Staff & Admins)
ALTER TABLE users 
    ADD COLUMN IF NOT EXISTS university_id VARCHAR(64) REFERENCES universities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS department_id VARCHAR(64) REFERENCES departments(id) ON DELETE RESTRICT;

-- Projects
ALTER TABLE projects 
    ADD COLUMN IF NOT EXISTS university_id VARCHAR(64) REFERENCES universities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS college_id VARCHAR(64) REFERENCES colleges(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS department_id VARCHAR(64) REFERENCES departments(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS abstract_embedding VECTOR(1024),
    ADD COLUMN IF NOT EXISTS abstract_embedding_binary BIT(1024);

ALTER TABLE projects
    DROP CONSTRAINT IF EXISTS fk_projects_team,
    ADD CONSTRAINT fk_projects_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

ALTER TABLE projects
    DROP CONSTRAINT IF EXISTS fk_projects_student,
    ADD CONSTRAINT fk_projects_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL;

-- Scan Reports Auditing & Tenancy
ALTER TABLE scan_reports
    ADD COLUMN IF NOT EXISTS university_id VARCHAR(64) REFERENCES universities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS college_id VARCHAR(64) REFERENCES colleges(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS department_id VARCHAR(64) REFERENCES departments(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS initiated_by VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL;

-- 3. High-Performance Scoping Indexes
CREATE INDEX IF NOT EXISTS idx_colleges_uni ON colleges(university_id);
CREATE INDEX IF NOT EXISTS idx_depts_college ON departments(college_id);
CREATE INDEX IF NOT EXISTS idx_users_hierarchy ON users(university_id, college_id, department_id);
CREATE INDEX IF NOT EXISTS idx_students_hierarchy ON students(university_id, college_id, department_id);
CREATE INDEX IF NOT EXISTS idx_projects_hierarchy ON projects(university_id, college_id, department_id);
CREATE INDEX IF NOT EXISTS idx_teams_hierarchy ON teams(university_id, college_id, department_id);
CREATE INDEX IF NOT EXISTS idx_projects_abstract_emb ON projects USING hnsw (abstract_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

COMMIT;
```

---

## Task 2: UI Permission Leak & Navigation Visibility Audit

### 2.1 Code Inspection of UI Chrome & Guards
- **File:** [frontend/src/Sidebar.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/Sidebar.tsx)
  * **Lines 40–48:** Static `navItems` configuration contains every single administrative page:
    ```typescript
    const navItems = [
      { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { to: "/", label: "Project Intake", icon: UploadCloud },
      { to: "/scan", label: "Plagiarism Scanner", icon: Search },
      { to: "/projects", label: "Projects", icon: FolderOpen },
      { to: "/teams", label: "Team Management", icon: Users },
      { to: "/users", label: "User Management", icon: UserCog },
      { to: "/settings", label: "Settings", icon: Settings },
    ];
    ```
  * **Lines 78–101:** `Sidebar` maps directly over `navItems` with **zero role filtering**:
    ```typescript
    {navItems.map(({ to, label, icon: Icon }) => { ... })}
    ```
    Students, faculty, and administrators all see identical sidebars.

- **File:** [frontend/src/App.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/App.tsx)
  * **Lines 46–59:** `ProtectedRoute` implementation:
    ```typescript
    function ProtectedRoute() {
      const [token, setToken] = React.useState(() => localStorage.getItem("auth_token"));
      ...
      if (!token) return <Navigate to="/login" replace />;
      return <Outlet />;
    }
    ```
    `ProtectedRoute` checks only for the existence of `auth_token`. It performs no validation of JWT claims, role validity, expiration, or authorization.
  * **Lines 120–134:** Every route is nested flatly under this unguarded `ProtectedRoute`:
    ```typescript
    <Route element={<ProtectedRoute />}>
      <Route element={<AppLayout />}>
        <Route path="/" element={<ProjectIntake />} />
        <Route path="/scan" element={<PlagiarismScanner />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/teams" element={<Teams />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        ...
      </Route>
    </Route>
    ```

### 2.2 Student Login & Navigation Traversal Trace
1. **Default Landing:** In [frontend/src/pages/Login.tsx:36](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/pages/Login.tsx#L36), when a user with role `student` logs in, they are redirected unconditionally to `/dashboard`:
   ```typescript
   navigate("/dashboard");
   ```
2. **Dashboard Leakage:** On `/dashboard`, `Dashboard.tsx` fetches `GET /api/dashboard/stats`. The student is shown institution-wide metrics (total projects, total scans, average plagiarism percentages, and system health).
3. **Manual URL Traversal:**
   - Navigating to `/scan`: `PlagiarismAnalysis.tsx` mounts without restriction. The student can view pairwise diffs and trigger comparisons.
   - Navigating to `/`: `plagiarism/index.tsx` mounts. The student sees the intake form, can trigger uploads, and can open `ScanHistoryModal`.
   - Navigating to `/users`: `Users.tsx` mounts. It triggers `GET /api/users`. While the backend blocks `list_users` with 403, the page structure, bulk import modal, and user creation form are rendered to the student.
   - Navigating to `/teams`: `Teams.tsx` mounts. The student can search all students across the system and dispatch mutation requests.
   - Navigating to `/settings`: `Settings.tsx` mounts and loads `GET /api/settings` (which has no backend auth). The student reads system threshold configurations.

---

### 2.3 Proposed React Router Guard & Sidebar Filtering Architecture

#### 1. Role-Filtered Sidebar (`frontend/src/Sidebar.tsx`)
```typescript
interface NavItem {
  to: string;
  label: string;
  icon: any;
  allowedRoles: Array<"ministry_admin" | "university_admin" | "college_admin" | "faculty" | "student">;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/", label: "Project Intake", icon: UploadCloud, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/scan", label: "Plagiarism Scanner", icon: Search, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/projects", label: "Projects & AI Search", icon: FolderOpen, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/teams", label: "My Team", icon: Users, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/users", label: "User Management", icon: UserCog, allowedRoles: ["ministry_admin", "university_admin", "college_admin"] },
  { to: "/settings", label: "Settings", icon: Settings, allowedRoles: ["ministry_admin", "university_admin"] },
];

// In Sidebar Component:
const currentRole = user?.role || "student";
const visibleNavItems = NAV_ITEMS.filter((item) => item.allowedRoles.includes(currentRole));
```

#### 2. Tiered Route Guard (`frontend/src/components/RoleGuard.tsx`)
```typescript
import { Navigate, Outlet } from "react-router-dom";

export function RoleGuard({ allowedRoles }: { allowedRoles: string[] }) {
  const token = localStorage.getItem("auth_token");
  const userStr = localStorage.getItem("user_data");
  
  if (!token || !userStr) {
    return <Navigate to="/login" replace />;
  }

  try {
    const user = JSON.parse(userStr);
    if (!allowedRoles.includes(user.role)) {
      // Default safe landing based on role
      return <Navigate to={user.role === "student" ? "/projects" : "/dashboard"} replace />;
    }
  } catch {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
```

#### 3. Route Configuration (`frontend/src/App.tsx`)
```tsx
<Routes>
  <Route element={<AppLayout />}>
    {/* Student & Academic Staff Shared Routes */}
    <Route element={<RoleGuard allowedRoles={["student", "faculty", "college_admin", "university_admin", "ministry_admin"]} />}>
      <Route path="/projects" element={<Projects />} />
      <Route path="/teams" element={<Teams />} />
    </Route>

    {/* Staff & Faculty Scanners */}
    <Route element={<RoleGuard allowedRoles={["faculty", "college_admin", "university_admin", "ministry_admin"]} />}>
      <Route path="/" element={<ProjectIntake />} />
      <Route path="/scan" element={<PlagiarismScanner />} />
      <Route path="/dashboard" element={<Dashboard />} />
    </Route>

    {/* Institutional User Administration */}
    <Route element={<RoleGuard allowedRoles={["college_admin", "university_admin", "ministry_admin"]} />}>
      <Route path="/users" element={<UsersPage />} />
    </Route>

    {/* System Configuration */}
    <Route element={<RoleGuard allowedRoles={["university_admin", "ministry_admin"]} />}>
      <Route path="/settings" element={<SettingsPage />} />
    </Route>
  </Route>
</Routes>
```

---

## Task 3: Backend API Authorization & Endpoint Security Audit

### 3.1 The Empty `require_role()` Vulnerability
In [app/dependencies.py:92-123](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/dependencies.py#L92-L123):
```python
def require_role(*allowed_roles: str):
    def _enforce(credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme)):
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        role = payload.get("role")
        ...
        if allowed_roles and role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return { ... }
    return _enforce
```
When endpoints declare `dependencies=[Depends(require_role())]` without parameters, `allowed_roles` is an empty tuple `()`. The check `if allowed_roles:` evaluates to `False`. The server extracts the token but **never verifies the role**. Any authenticated user, including `student`, is granted full execution privileges.

### 3.2 Inventory of Vulnerable & Open Endpoints

```
========================================================================================================================
ROUTER AUDIT: VULNERABLE AND OPEN ENDPOINTS
========================================================================================================================
File Path         | Line | HTTP Method & Path                         | Current RBAC Dependency      | Security Severity
------------------|------|--------------------------------------------|------------------------------|------------------
settings.py       | L15  | GET  /api/settings                         | NONE (Publicly Exposed)      | HIGH: Info Leak
dashboard.py      | L20  | GET  /api/system/health                    | NONE (Publicly Exposed)      | LOW: Health Check
projects.py       | L166 | GET  /api/plagiarism/projects/check        | NONE (Publicly Exposed)      | MEDIUM: Recon
scanner.py        | L41  | GET  /api/plagiarism/scan-stream/{pid}     | NONE (Publicly Exposed)      | HIGH: Stream Snooping
------------------|------|--------------------------------------------|------------------------------|------------------
compare.py        | L91  | POST /api/plagiarism/compare-projects      | Depends(require_role()) [EMPTY]| CRITICAL: Student Access
compare.py        | L164 | POST /api/plagiarism/compare-files         | Depends(require_role()) [EMPTY]| CRITICAL: Student Access
compare.py        | L225 | POST /api/plagiarism/compare-direct-files  | Depends(require_role()) [EMPTY]| CRITICAL: Student Access
dashboard.py      | L30  | GET  /api/dashboard/stats                  | Depends(require_role()) [EMPTY]| HIGH: Data Leak
deep_scan.py      | L51  | POST /api/plagiarism/deep-scan             | Depends(require_role()) [EMPTY]| CRITICAL: GPU/CPU Exhaustion
deep_scan.py      | L163 | POST /api/plagiarism/deep-scan-bulk        | Depends(require_role()) [EMPTY]| CRITICAL: GPU/CPU Exhaustion
history.py        | L49  | GET  /api/plagiarism/history               | Depends(require_role()) [EMPTY]| HIGH: History Leak
history.py        | L56  | GET  /api/plagiarism/history/{report_id}   | Depends(require_role()) [EMPTY]| HIGH: Report Leak
history.py        | L84  | DELETE /api/plagiarism/history/{report_id} | Depends(require_role()) [EMPTY]| CRITICAL: Student Deletes Logs!
projects.py       | L18  | GET  /api/plagiarism/projects              | Depends(require_role()) [EMPTY]| HIGH: Full Project Catalog
projects.py       | L48  | PUT  /api/plagiarism/projects/{pid}        | Depends(require_role()) [EMPTY]| CRITICAL: Student Modifies Projs
projects.py       | L96  | DELETE /api/plagiarism/projects/{pid}     | Depends(require_role()) [EMPTY]| CRITICAL: Student Deletes Projs
projects.py       | L117 | GET  /api/plagiarism/projects/{pid}/files  | Depends(require_role()) [EMPTY]| HIGH: File Contents Leak
projects.py       | L185 | POST /api/plagiarism/projects/semantic-srch| Depends(require_role()) [EMPTY]| OK for Student (Spec 2.A)
scanner.py        | L73  | POST /api/plagiarism/upload-scan           | Depends(require_role()) [EMPTY]| CRITICAL: Student Runs Scans
scanner.py        | L118 | POST /api/plagiarism/upload-scan-stream    | Depends(require_role()) [EMPTY]| CRITICAL: Student Runs Scans
scanner.py        | L198 | POST /api/plagiarism/upload-zip-stream     | Depends(require_role()) [EMPTY]| CRITICAL: Student Uploads Zips
scanner.py        | L291 | POST /api/plagiarism/git-scan              | Depends(require_role()) [EMPTY]| CRITICAL: SSRF / Git Clones
scanner.py        | L317 | POST /api/plagiarism/git-scan-stream       | Depends(require_role()) [EMPTY]| CRITICAL: SSRF / Git Clones
scanner.py        | L372 | POST /api/plagiarism/scan-stream           | Depends(require_role()) [EMPTY]| CRITICAL: Scanner Execution
scanner.py        | L411 | POST /api/plagiarism/scan                  | Depends(require_role()) [EMPTY]| CRITICAL: Scanner Execution
teams.py          | L34  | GET  /api/teams                            | Depends(require_role()) [EMPTY]| HIGH: Global Team View
teams.py          | L42  | POST /api/teams                            | Depends(require_role()) [EMPTY]| CRITICAL: Student Creates Teams
teams.py          | L56  | GET  /api/teams/{team_id}                  | Depends(require_role()) [EMPTY]| HIGH: Unscoped Team Detail
teams.py          | L74  | PUT  /api/teams/{team_id}                  | Depends(require_role()) [EMPTY]| CRITICAL: Student Updates Teams
teams.py          | L92  | DELETE /api/teams/{team_id}               | Depends(require_role()) [EMPTY]| CRITICAL: Student Deletes Teams
teams.py          | L110 | POST /api/teams/{team_id}/members          | Depends(require_role()) [EMPTY]| CRITICAL: Arbitrary Enrollment
teams.py          | L133 | DELETE /api/teams/{team_id}/members/{sid}  | Depends(require_role()) [EMPTY]| CRITICAL: Student Kicks Members
teams.py          | L157 | GET  /api/teams/students/search            | Depends(require_role()) [EMPTY]| HIGH: Student Enumeration
========================================================================================================================
```

---

### 3.3 Target 4-Tier RBAC Endpoint Matrix

```
========================================================================================================================
TARGET 4-TIER BACKEND AUTHORIZATION MATRIX
========================================================================================================================
Endpoint Route                               | Ministry Admin | University Admin | College Admin | Faculty | Student
---------------------------------------------|:--------------:|:----------------:|:-------------:|:-------:|:-------:
GET    /api/settings                         |       ✅       |        ✅        |      ❌       |   ❌    |   ❌
PUT    /api/settings                         |       ✅       |        ❌        |      ❌       |   ❌    |   ❌
GET    /api/dashboard/stats                  |    ✅ Global   |   ✅ University  |   ✅ College  | ✅ Dept |   ❌
POST   /api/plagiarism/scan*                 |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
POST   /api/plagiarism/git-scan*             |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
POST   /api/plagiarism/compare-*             |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
POST   /api/plagiarism/deep-scan*            |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
GET    /api/plagiarism/history*              |    ✅ Global   |   ✅ University  |   ✅ College  | ✅ Dept |   ❌
DELETE /api/plagiarism/history/{id}          |       ✅       |        ❌        |      ❌       |   ❌    |   ❌
GET    /api/plagiarism/projects              |    ✅ Global   |   ✅ University  |   ✅ College  | ✅ Dept | 👁️ Own Only
POST   /api/plagiarism/projects              |       ✅       |        ✅        |      ✅       |   ✅    |   ✅
PUT    /api/plagiarism/projects/{id}         |       ✅       |        ✅        |      ✅       |   ✅    | 👁️ Own Draft
DELETE /api/plagiarism/projects/{id}         |       ✅       |        ✅        |      ✅       |   ❌    |   ❌
POST   /api/plagiarism/projects/{id}/approve |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
POST   /api/plagiarism/projects/semantic-srch|       ✅       |        ✅        |      ✅       |   ✅    |   ✅
GET    /api/teams                            |    ✅ Global   |   ✅ University  |   ✅ College  | ✅ Dept | 👁️ Own Team
POST   /api/teams                            |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
PUT    /api/teams/{id}                       |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
DELETE /api/teams/{id}                       |       ✅       |        ✅        |      ✅       |   ❌    |   ❌
POST   /api/teams/{id}/members               |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
DELETE /api/teams/{id}/members/{sid}         |       ✅       |        ✅        |      ✅       |   ✅    |   ❌
GET    /api/users                            |    ✅ Global   |   ✅ University  |   ✅ College  |   ❌    |   ❌
POST   /api/users                            |    ✅ Global   |   ✅ University  |   ✅ College  |   ❌    |   ❌
PUT    /api/users/{id}                       |    ✅ Global   |   ✅ University  |   ✅ College  |   ❌    |   ❌
DELETE /api/users/{id}                       |    ✅ Global   |   ✅ University  |   ✅ College  |   ❌    |   ❌
========================================================================================================================
```

---

## Task 4: Role Assignment Governance & Self-Lockout Prevention

### 4.1 Capability Matrix vs. Hierarchical Role-and-Scope Assignment
- **Dynamic Capability Matrix (Per-permission DB flags):** Gives individual checkboxes (`can_run_deep_scan`, `can_export_pdf`, etc.).
  * *Drawbacks:* High database overhead, severe permission drift, difficult compliance auditing, and administrative fatigue for university deans.
- **Hierarchical Role-and-Scope Assignment (Recommended):**
  * A user is assigned a single **Role** coupled with an **Institutional Scope** tuple:
    $$\text{User} = \langle \text{Role}, \text{university\_id}, \text{college\_id}, \text{department\_id} \rangle$$
  * *Advantages:* Maps directly onto academic governance laws; guarantees deterministic row-level authorization; simple to audit and maintain.

---

### 4.2 Audit of Current User Endpoints in `app/routers/users.py`
- **File:** [app/routers/users.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py)

#### 1. Severe Scope Boundary Flaws & Privilege Escalation
In `POST /api/users` ([users.py:80-88](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py#L80-L88)) and `PUT /api/users/{user_id}` ([users.py:203-218](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py#L203-L218)):
```python
current_user: dict = Depends(require_role("ministry_admin", "college_admin"))
...
valid_roles = {"ministry_admin", "college_admin", "faculty", "student"}
if payload.role not in valid_roles:
    raise HTTPException(status_code=400, detail="...")
```
- **Vulnerability:** A `college_admin` can create a user with `role: "ministry_admin"`, or edit an existing user to elevate them to `ministry_admin`!
- **Cross-Tenant Mutation:** A `college_admin` of College A can update or delete users from College B because there is no verification that `current_user["college_id"] == target_user["college_id"]`.

#### 2. Self-Lockout & Self-Deletion Vulnerabilities
In `PUT /api/users/{user_id}` ([users.py:212-214](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py#L212-L214)):
```python
if payload.role is not None and current_user["user_id"] == user_id and current_user["role"] != payload.role:
    raise HTTPException(status_code=403, detail="Admins cannot modify their own roles.")
```
While this restricts immediate role changes on oneself, it is critically incomplete:
1. **Self-Deletion Unprotected:** In `DELETE /api/users/{user_id}` ([users.py:259-274](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py#L259-L274)), there is **no check on `user_id == current_user["user_id"]`**. An administrator can delete their own account.
2. **Sole Super Admin Elimination:** Neither `PUT` nor `DELETE` checks whether the target user is the **last active Ministry Admin**. A secondary admin could demote or delete the primary Ministry Admin, permanently locking the institution out of global governance.

---

### 4.3 Robust Role Assignment & Self-Lockout Governance Specification

```
====================================================================================================
DELEGATION BOUNDARIES (WHO CAN ASSIGN WHAT)
====================================================================================================
Caller Role       | Permitted Assignable Roles                      | Enforced Institutional Scope
------------------|-------------------------------------------------|-------------------------------
ministry_admin    | university_admin, college_admin, faculty, student| Global (Any institution)
university_admin  | college_admin, faculty, student                | Target must match caller's university_id
college_admin     | faculty, student                                | Target must match caller's college_id & university_id
faculty / student | NONE                                            | 403 Forbidden
====================================================================================================
```

#### Enforcement Implementation in `app/routers/users.py`:
```python
def validate_role_assignment(caller: dict, target_role: str, target_uni: str, target_college: str):
    caller_role = caller["role"]
    
    # 1. Delegation hierarchy check
    allowed_assignments = {
        "ministry_admin": {"university_admin", "college_admin", "faculty", "student"},
        "university_admin": {"college_admin", "faculty", "student"},
        "college_admin": {"faculty", "student"},
    }
    if target_role not in allowed_assignments.get(caller_role, set()):
        raise HTTPException(
            status_code=403, 
            detail=f"Role '{caller_role}' cannot create or assign role '{target_role}'."
        )

    # 2. Scope boundary check
    if caller_role == "university_admin":
        if target_uni != caller["university_id"]:
            raise HTTPException(status_code=403, detail="Cannot assign users outside your university.")
            
    if caller_role == "college_admin":
        if target_uni != caller["university_id"] or target_college != caller["college_id"]:
            raise HTTPException(status_code=403, detail="Cannot assign users outside your assigned college.")

def check_self_lockout_and_last_admin(db, caller: dict, target_user_id: str, is_delete: bool = False, new_role: str = None):
    # Self-modification of privileges
    if caller["user_id"] == target_user_id:
        if is_delete:
            raise HTTPException(status_code=403, detail="Self-deletion is prohibited to prevent lockout.")
        if new_role and new_role != caller["role"]:
            raise HTTPException(status_code=403, detail="You cannot modify or demote your own administrative role.")

    # Prevent elimination of the last Ministry Admin
    target_user = db.get_user_by_id(target_user_id)
    if target_user and target_user.get("role") == "ministry_admin":
        if is_delete or (new_role and new_role != "ministry_admin"):
            active_super_admins = db.count_users(role="ministry_admin")
            if active_super_admins <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Operation rejected: Cannot delete or demote the sole remaining Ministry Admin."
                )
```

---

## Task 5: Student AI Semantic Proposal Search Audit (Spec Step 2.A)

### 5.1 Deep Architectural Audit of `POST /api/plagiarism/projects/semantic-search`
- **File:** [app/routers/projects.py:184-324](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/projects.py#L184-L324)

#### Flaw 1: Bypassing pgvector & In-Memory Deserialization Bottleneck
Lines 216–258:
```python
sql = """
    SELECT pf.project_id, pf.relative_path, pf.embedding, pf.embedding_model,
           p.name, p.title, p.abstract, p.department, p.year, p.university, p.status
    FROM project_files pf
    JOIN projects p ON p.id = pf.project_id
    WHERE pf.file_type = 'text' AND pf.embedding IS NOT NULL
"""
...
rows = cur.fetchall()
for r in rows:
    emb_raw = r[2]
    emb = PgVectorStore._parse_embedding(emb_raw)
    sim = float(np.dot(q_emb, emb))
```
- **Finding:** The endpoint executes **no vector operations in PostgreSQL**. It selects every stored text embedding as raw text/JSON over the database connection, parses the text into float arrays using `json.loads` in Python, and calculates dot products via NumPy.
- **Impact:** Memory consumption scales linearly with corpus size. If the repository stores 10,000 files, the server transfers ~160 MB of text per search and locks Python's GIL.

#### Flaw 2: Synchronous Neural Network Encoding in the Live Request Loop
Lines 279–291:
```python
# Also check projects with abstracts in the projects table
cur.execute(
    "SELECT id, name, title, abstract, department, year, university, status FROM projects WHERE abstract IS NOT NULL AND TRIM(abstract) != ''"
)
for r in cur.fetchall():
    ...
    abs_text = (r[3] or "").strip()
    if not abs_text:
        continue
    abs_emb = model.encode(abs_text[:2000], convert_to_numpy=True)
    abs_emb = PgVectorStore._normalize_and_pad_1d(abs_emb, 1024)
    sim = float(np.dot(q_emb, abs_emb))
```
- **Finding:** Because the `projects` table lacks an embedding column, **the developers invoke `model.encode(abs_text[:2000])` synchronously for every project abstract in the database during every single user search!**
- **Impact:** `BAAI/bge-m3` forward inference on a 2,000-character text takes ~150–400 ms on CPU (~20–40 ms on GPU).
  * 10 projects: ~2.5 seconds latency.
  * 100 projects: ~25 seconds latency.
  * 1,000 projects: ~250 seconds latency (Request Timeout / Server Collapse).

#### Flaw 3: Complete Absence of Arabic Text Normalization
- In [projects.py:192](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/projects.py#L192) and [projects.py:286](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/projects.py#L286), the code only performs `.strip()`.
- The repository already possesses an Arabic text normalizer in [plagiarism_engine/arabic_preprocessor.py:31-38](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/plagiarism_engine/arabic_preprocessor.py#L31-L38):
  ```python
  def normalize_arabic(text: str) -> str:
      if not text:
          return ""
      text = DIACRITICS.sub('', text)
      text = TATWEEL.sub('', text)
      text = text.translate(ARABIC_NORM_MAP)
      return text
  ```
- **Finding:** Neither the query nor the abstracts are passed through `normalize_arabic()`. As a result, diacritics (تَشْكِيل), tatweel (كَشِيدَة: `تطــــوير` vs `تطوير`), and alef variants (`إدارة` vs `ادارة`) produce divergent embeddings, resulting in missed plagiarism matches and false negatives.

---

### 5.2 Bulletproof Hardening Plan for Proposal Search

```
                                  PROPOSAL SEARCH HARDENING PIPELINE
                                  ==================================

1. INTAKE / UPDATE PHASE (Async / Background):
   Project Proposal Abstract 
          │
          ▼
   normalize_arabic()  ──────► model.encode(text) ──────► Store in projects.abstract_embedding
   (Strip diacritics/kashida)   (BAAI/bge-m3 1024-d)       (PostgreSQL VECTOR(1024) with HNSW Index)

------------------------------------------------------------------------------------------------------

2. LIVE QUERY PHASE (Sub-10ms Execution):
   User Search Query (Arabic / English)
          │
          ▼
   normalize_arabic()  ──────► model.encode(query) ─────► Direct SQL Cosine Query (<=>)
                               (1 inference only)         SELECT id, 1 - (abstract_embedding <=> q)
                                                          FROM projects WHERE abstract_embedding IS NOT NULL
                                                          ORDER BY abstract_embedding <=> q LIMIT 20;
```

#### Optimized SQL Search Endpoint (`app/routers/projects.py`):
```python
from plagiarism_engine.arabic_preprocessor import normalize_arabic

@router.post("/api/plagiarism/projects/semantic-search", dependencies=[Depends(require_role("student", "faculty", "college_admin", "university_admin", "ministry_admin"))])
async def semantic_project_search(payload: SemanticSearchRequest):
    raw_query = (payload.query or "").strip()
    if not raw_query:
        return {"query": "", "total_found": 0, "projects": []}

    # 1. Normalize query (vital for Arabic & bilingual terms)
    cleaned_query = normalize_arabic(raw_query)

    loop = asyncio.get_running_loop()
    db = get_db()

    def _execute_vector_search():
        from plagiarism_engine.vector_store import model_pool, DOMAIN_MODEL_KEYS
        model, model_name = model_pool.get_model_with_name(DOMAIN_MODEL_KEYS["text"])
        if model is None:
            raise HTTPException(status_code=503, detail="Search model is initializing.")

        # 2. Exactly ONE forward pass for the user query
        q_emb = model.encode(cleaned_query, convert_to_numpy=True).flatten().tolist()

        conn = db._get_connection()
        try:
            cur = conn.cursor()
            # 3. Native pgvector cosine similarity (<=>) accelerated by HNSW index
            sql = """
                SELECT id, name, title, abstract, department, year, university, status,
                       1 - (abstract_embedding <=> %(emb)s::vector) AS sim
                FROM projects
                WHERE abstract_embedding IS NOT NULL
            """
            params = {"emb": str(q_emb)}
            if payload.department:
                sql += " AND LOWER(department) = LOWER(%(dept)s)"
                params["dept"] = payload.department
            if payload.year:
                sql += " AND year = %(year)s"
                params["year"] = payload.year
            if payload.university:
                sql += " AND LOWER(university) LIKE LOWER(%(uni)s)"
                params["uni"] = f"%{payload.university}%"

            sql += " AND (1 - (abstract_embedding <=> %(emb)s::vector)) >= %(thresh)s "
            params["thresh"] = payload.threshold or 0.15

            sql += " ORDER BY abstract_embedding <=> %(emb)s::vector ASC LIMIT %(top_k)s;"
            params["top_k"] = payload.top_k or 20

            cur.execute(sql, params)
            rows = cur.fetchall()
            ...
```

---

## Conclusion & Recommended Remediation Roadmap

| Step | Milestone | Priority | Effort | Key Benefit |
|:---:|---|:---:|:---:|---|
| **Phase 1** | **Patch `require_role()` & Endpoint Dependencies** | **P0 - Urgent** | 1 day | Eliminates unauthorized administrative access by students |
| **Phase 2** | **Deploy React Router `RoleGuard` & Filter Sidebar** | **P0 - Urgent** | 1 day | Stops UI permission leaks and routes students to `/projects` |
| **Phase 3** | **Enforce Role Assignment Scope & Self-Lockout Guards** | **P1 - High** | 2 days | Prevents privilege escalation and administrative self-lockout |
| **Phase 4** | **Pre-embed Abstracts & Accelerate pgvector HNSW** | **P1 - High** | 2 days | Drops search latency from tens of seconds to $<15\text{ ms}$ |
| **Phase 5** | **Execute Hierarchy DB Migration (Colleges, Depts, FKs)** | **P2 - Medium** | 3 days | Establishes strict institutional tenancy across all entities |
