# System Users & Role-Based Access Control (RBAC) Testing Guide

This document details the configured user accounts, roles, access levels, authentication mechanisms, and step-by-step verification flows for testing the Plagiarism Detection Engine.

---

## 1. Test Accounts & Login Credentials

| Role | Login Identifier (Email or Enrollment ID) | Password | Display Name | Organization / Scope |
|---|---|:---:|---|---|
| **Ministry Admin**<br>*(Super Admin)* | `admin@ministry.gov`<br>*(or `admin@test.com`)* | `admin123` | Admin | **Global Access** (All universities, colleges, users, system settings) |
| **College Admin** | `dean@engineering.edu` | `password123` | Prof. Tariq | **College Level** (College of Engineering: manages users, teams, and projects) |
| **Faculty / Dept Head** | `dr.sarah@cs.edu` | `password123` | Dr. Sarah | **Academic Staff** (Computer Science: reviews proposals, approves/rejects projects, triggers scans) |
| **Student** | `20240001` *(Enrollment ID)* | `password123` | Mustafa Ahmed | **Student Access** (Searches proposals via AI semantic search, views own projects, joins teams) |

> [!NOTE]
> **Unified Authentication Pipeline:**
> - Staff and admin accounts (`ministry_admin`, `college_admin`, `faculty`) authenticate using their **email address**.
> - Student accounts authenticate using their **Enrollment ID** (`20240001`) directly in the login identifier box.

---

## 2. Role-Based Access Control (RBAC) Matrix

| Feature / Action | Ministry Admin | College Admin | Faculty / Dept Head | Student |
|---|:---:|:---:|:---:|:---:|
| **Plagiarism Scanner (`/scan`)** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ❌ Restricted (403) |
| **Direct Two-Document Comparison** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ❌ Restricted (403) |
| **Scan History & Audit Report Export** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ❌ Restricted (403) |
| **Project Intake & Upload (`/plagiarism`)** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ❌ Restricted (403) |
| **Faculty Project Approval / Rejection** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ❌ Restricted (403) |
| **Project Repository (`/projects`)** | ✅ All Projects | ✅ College Projects | ✅ Department Projects | 👁️ Only Own Submissions |
| **AI Semantic Proposal Search (`/projects`)** | ✅ Full Access | ✅ Full Access | ✅ Full Access | ✅ **Full Access** *(Spec 2.A)* |
| **User Management (`/users`)** | ✅ Full Access | ✅ College Users | ❌ Restricted (403) | ❌ Restricted (403) |
| **Bulk CSV/Excel Student Import** | ✅ Full Access | ✅ College Scope | ❌ Restricted (403) | ❌ Restricted (403) |
| **Team Management (`/teams`)** | ✅ Full Access | ✅ Full Access | ✅ Full Access | 👁️ View Assigned Team |

---

## 3. Recommended Step-by-Step Testing Walkthrough

### Test Scenario A: Student Experience (`20240001` / `password123`)
1. Log in at `/login` with identifier `20240001` and password `password123`.
2. Navigate to **Projects** (`/projects`).
3. Click the **🤖 AI Semantic Proposal Search** tab at the top.
4. Input a test topic / problem statement in **English** or **Arabic**:
   - *English Example:* `"Autonomous robotics navigation utilizing LIDAR and computer vision for obstacle avoidance in warehouses"`
   - *Arabic Example:* `"نظام كشف الانتحال الأكاديمي للنصوص والمشاريع البرمجية باستخدام الذكاء الاصطناعي"`
5. Adjust the **Min Similarity Threshold** slider (e.g., 20%) and click **Search Existing Projects**.
6. Verify ranked matching projects, calibrated similarity percentages, matched document files, and abstract previews.
7. Attempt to navigate directly to `/users` or `/plagiarism` and verify that administrative access is blocked.

### Test Scenario B: Faculty & Department Head (`dr.sarah@cs.edu` / `password123`)
1. Log in at `/login` with `dr.sarah@cs.edu` and `password123`.
2. Go to **Projects** (`/projects`) → locate projects with status `PENDING`.
3. Click the green **Approve** button (`CheckCircle2`) to approve the project title/abstract.
4. Navigate to **Plagiarism Scanner** (`/scan`):
   - Test **Direct Two-Document Comparison** by switching between `[Upload File]` and `[Database Project File]`.
   - Run a pairwise comparison and view the interactive visual diff.

### Test Scenario C: College Administrator (`dean@engineering.edu` / `password123`)
1. Log in at `/login` with `dean@engineering.edu` and `password123`.
2. Navigate to **Users** (`/users`):
   - Click **Add User** → change role to **Student**. Notice the form adapts to ask for Enrollment ID, Department, College, and temporary password (default `123456`).
   - Click **Bulk Import** → click **Download Template (.csv)** to verify `students_template.csv`.
   - Upload or paste a CSV file to preview parsed students and execute batch insertion.
3. Navigate to **Teams** (`/teams`):
   - Click on an existing team or create a new team.
   - Use the **Search & Add Student** autocomplete input to search by student name or enrollment number.
   - Click **+ Add** to assign the student to the team.

### Test Scenario D: Ministry Administrator (`admin@ministry.gov` / `admin123`)
1. Log in at `/login` with `admin@ministry.gov` and `admin123`.
2. Verify full global administrative visibility across all universities, colleges, projects, and users.
3. Run or review scans, view the **Scan History & Audit Logs** modal, and export `.txt` audit reports.

---

## 4. Database Schema Reference

- **`users` Table:** Stores staff and administrators (`ministry_admin`, `college_admin`, `faculty`).
  - Columns: `id`, `name`, `email`, `password_hash`, `role`, `college_id`, `created_at`, `requires_password_change`.
- **`students` Table:** Stores enrolled students (`student` role).
  - Columns: `id`, `enrollment_number`, `name`, `college_id`, `team_id`, `created_at`, `password_hash`, `requires_password_change`.
- **Password Hashing:** Passwords are salted and hashed using `bcrypt`.
- **Session Tokens:** JWT HS256 tokens carrying `user_id`, `role`, `email`/`enrollment_number`, and `requires_password_change` claims.
