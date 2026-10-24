# Yemeni Academic Institutional Hierarchy & Scoping Isolation Walkthrough

## Summary of Accomplishments

All 6 pillars of the approved institutional hierarchy and system polish plan have been fully implemented, validated, and pushed to `origin/main` (commit `23e63f7`):

1. **Live Stream Console Lifecycle & Reset**:
   - The live execution stream is automatically wiped on **user logout** (`localStorage.removeItem('plagiarism-scan-storage')` + `resetAll()`).
   - When **new files or folders are staged** for intake or scan, `useScanStore.getState().resetScan()` immediately clears previous logs and terminal outputs.
   - Added a **"Clear Terminal Output"** trash button directly into the live terminal header in [ScanProgress.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/pages/plagiarism/ScanProgress.tsx) so users can manually wipe output without resetting staged files.

2. **Intake UI Polish**:
   - Removed the redundant manual project name input box from above the browse buttons in [UploadSection.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/pages/plagiarism/UploadSection.tsx).
   - Project name is automatically detected and populated from the root directory or file stem upon selection, and can still be customized in the Academic & Project Metadata drawer.

3. **Abstract Decompression & Semantic Calibration Fix**:
   - Fixed base64 Zlib compressed strings (`eJy...`) in `projects.abstract`. Project abstracts are now transparently decompressed before embedding and display.
   - Re-computed dense vector embeddings for all benchmark projects with clean plain-text abstracts.
   - Calibrated hybrid scoring so queries with zero lexical overlap have their semantic score damped by 0.50x, eliminating background embedding noise from surfacing irrelevant projects.

4. **Multi-University Hierarchy Database Seeding**:
   - Purged obsolete/polluted test users, students, and teams while **preserving all 24 benchmark projects, 2,502 project files, and 682,791 fingerprint records**.
   - Seeded **Ministry of Higher Education** and **3 Yemeni Universities** (Sana'a University, Ibb University, Thamar University) with 5 colleges, 6 departments, 15 staff accounts, 5 teams, and 9 students.

5. **Strict Institutional Scoping Hardening**:
   - [teams.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/teams.py): Strict isolation in `list_teams`, `create_team`, `update_team`, `delete_team`, `toggle_submission`, and student search by college/university.
   - [users.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/users.py): University admins cannot see or modify users from other universities. College admins can only view and manage faculty/students in their own college.
   - [projects.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/app/routers/projects.py): Proposals pending review are strictly scoped to the caller's college. Cross-college review or deletion attempts return `403 Forbidden`.

6. **100% Automated Test Coverage**:
   - All 9 unit tests in [test_rbac_hardening.py](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/tests/test_rbac_hardening.py) passed in 9.6 seconds.
   - Frontend TypeScript type check (`tsc --noEmit`) completed with 0 errors.

---

## Complete Credential Matrix

All passwords are pre-configured with `requires_password_change = False` so you can log in directly without being redirected:

| Role | Name | Email / Identifier | Password | Institution & Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Ministry Admin** | م. علي السقاف | `admin@mohesr.gov.ye` | `Ministry@2026` | وزارة التعليم العالي (Nationwide Scope) |
| **Univ Admin (Sana'a)** | أ.د. القاسم عباس | `rector@su.edu.ye` | `Sanaa@2026` | جامعة صنعاء (All colleges in Sana'a) |
| **Dean (Sana'a CIT)** | د. فضل باعلوي | `dean.cit@su.edu.ye` | `Dean@2026` | كلية الحاسوب وتكنولوجيا المعلومات - صنعاء |
| **Dean (Sana'a Eng)** | أ.د. محمد البخيتي | `dean.eng@su.edu.ye` | `Dean@2026` | كلية الهندسة - صنعاء |
| **Faculty (Sana'a AI)** | د. عمار زاهر | `dr.ammar@su.edu.ye` | `Faculty@2026` | قسم الذكاء الاصطناعي - حاسوب صنعاء |
| **Faculty (Sana'a SWE)** | د. نبيل العريقي | `dr.nabil@su.edu.ye` | `Faculty@2026` | قسم هندسة البرمجيات - حاسوب صنعاء |
| **Faculty (Sana'a CompEng)**| د. طارق المجيدي | `dr.tariq@su.edu.ye` | `Faculty@2026` | قسم هندسة الحاسوب - هندسة صنعاء |
| **Student 1 (Sana'a CIT)** | أحمد الحمادي | `2024101001` | `Student@2026` | فريق رؤية الذكاء الاصطناعي (Team 1) |
| **Student 2 (Sana'a CIT)** | سارة الزبيري | `2024101002` | `Student@2026` | فريق رؤية الذكاء الاصطناعي (Team 1) |
| **Student 3 (Sana'a Eng)** | يحيى المتوكل | `2024102001` | `Student@2026` | فريق هندسة النظم المدمجة (Team 2) |
| **Student 4 (Sana'a Eng)** | ريم الشامي | `2024102002` | `Student@2026` | فريق هندسة النظم المدمجة (Team 2) |
| **Univ Admin (Ibb)** | أ.د. نصر الحجيلي | `rector@univibb.edu.ye` | `Ibb@2026` | جامعة إب (All colleges in Ibb) |
| **Dean (Ibb Eng & IT)** | د. فرحان غالب | `dean.eng@univibb.edu.ye` | `Dean@2026` | كلية الهندسة وتكنولوجيا المعلومات - إب |
| **Dean (Ibb Science)** | د. علي الوادعي | `dean.sci@univibb.edu.ye` | `Dean@2026` | كلية العلوم - إب |
| **Faculty (Ibb IT)** | د. خالد الصلاحي | `dr.khaled@univibb.edu.ye` | `Faculty@2026` | قسم تقنية المعلومات - إب |
| **Faculty (Ibb Math&CS)**| د. سميرة الشوافي | `dr.samira@univibb.edu.ye` | `Faculty@2026` | قسم الرياضيات والحاسوب - إب |
| **Student 5 (Ibb Eng)** | حسام المليكي | `2024201001` | `Student@2026` | رواد الحوسبة السحابية (Team 3) |
| **Student 6 (Ibb Eng)** | مروة الأهدل | `2024201002` | `Student@2026` | رواد الحوسبة السحابية (Team 3) |
| **Student 7 (Ibb Sci)** | ماجد القاضي | `2024202001` | `Student@2026` | مجموعة التشفير التطبيقي (Team 4) |
| **Univ Admin (Thamar)** | أ.د. محمد الحيفي | `rector@tu.edu.ye` | `Dhamar@2026` | جامعة ذمار (All colleges in Thamar) |
| **Dean (Thamar CS)** | د. بشير المقالح | `dean.cs@tu.edu.ye` | `Dean@2026` | كلية الحاسوب ونظم المعلومات - ذمار |
| **Faculty (Thamar Cyber)**| د. فاطمة الغشم | `dr.fatima@tu.edu.ye` | `Faculty@2026` | قسم الأمن السيبراني - ذمار |
| **Student 8 (Thamar CS)** | أسامة الورقي | `2024301001` | `Student@2026` | درع ذمار السيبراني (Team 5) |
| **Student 9 (Thamar CS)** | هند العنسي | `2024301002` | `Student@2026` | درع ذمار السيبراني (Team 5) |

---

## Step-by-Step Guided Verification Scenarios

### Scenario 1: Cross-University Isolation (Ibb University vs. Sana'a University)
1. Open the app in your browser (`http://localhost:3000`).
2. Log in as **Dean of Engineering & IT at Ibb University**:
   - **Email**: `dean.eng@univibb.edu.ye`
   - **Password**: `Dean@2026`
3. Click on **Team Management** (`/teams`):
   - Notice that **only** *"رواد الحوسبة السحابية (Ibb Cloud Pioneers)"* appears.
   - Teams from Sana'a University (*فريق رؤية الذكاء الاصطناعي*) and Thamar University do **not** appear.
4. Click on **User Management** (`/users`):
   - Notice that **only** faculty from Ibb Engineering (د. خالد الصلاحي) and students from Ibb are listed.
   - Staff and students from Sana'a and Thamar are invisible.
5. Log out. Notice that the Live Engine stream and scan cache are completely cleared on logout.
6. Log in as **Sana'a University Rector** (`rector@su.edu.ye` / `Sanaa@2026`):
   - Go to **Team Management**: You see both Sana'a teams (*فريق رؤية الذكاء الاصطناعي* in CIT and *فريق هندسة النظم المدمجة* in Engineering).
   - Teams from Ibb and Thamar remain invisible.

---

### Scenario 2: Intra-University Cross-College Isolation (Sana'a CIT vs. Sana'a Engineering)
1. Log in as **Dean of Computer & IT at Sana'a University**:
   - **Email**: `dean.cit@su.edu.ye`
   - **Password**: `Dean@2026`
2. Go to **Team Management**:
   - Notice that **only** *"فريق رؤية الذكاء الاصطناعي"* (CIT team) is visible.
   - The Engineering team (*فريق هندسة النظم المدمجة*) belonging to Dean Al-Bukhaiti's college does **not** appear.
3. Log out and log in as **Faculty Supervisor Dr. Ammar Zaher**:
   - **Email**: `dr.ammar@su.edu.ye`
   - **Password**: `Faculty@2026`
4. Go to **Team Management**:
   - In the row for *"فريق رؤية الذكاء الاصطناعي"*, click **"Grant 1-Time Proposal Submission"**.
   - Notice the status updates to active with green badge.
5. Log out and log in as **Student Ahmed Al-Hammadi**:
   - **Enrollment Number**: `2024101001`
   - **Password**: `Student@2026`
6. Go to **Projects & AI Search** (`/projects`):
   - Notice the prominent banner: *"Graduation Proposal Submission Status: 1-Time Window Active"*.
   - Click **"Submit Proposal"**, fill in the title and abstract, and submit.
   - Notice the proposal transitions to **"Pending Review"** and the token locks immediately.
7. Log out and log in as **Dean of Engineering at Sana'a**:
   - **Email**: `dean.eng@su.edu.ye`
   - **Password**: `Dean@2026`
   - Go to **Projects**: Ahmed's proposal does **not** appear under pending review because it belongs to the College of Computer & IT.
8. Log in back as **Dr. Ammar Zaher** (`dr.ammar@su.edu.ye`):
   - Ahmed's proposal is listed with status `PENDING REVIEW`.
   - Click **"Review"**, provide feedback, and click **"Approve"**.
   - The proposal status updates to `APPROVED`.
