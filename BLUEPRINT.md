# Ministry System Blueprint & Source of Truth

This document serves as the absolute source of truth for the Ministry-Scale Graduation Project Plagiarism Engine. It defines the architecture, algorithms, data models, and the UI/UX roadmap. Any future changes to algorithms or database structure must be reflected here first.

---

## 1. System Overview
A highly scalable, performant system designed for a Ministry of Higher Education to track, manage, and analyze graduation projects across colleges. The project is developed in two phases:
* **Phase 1 (MVP):** Core Plagiarism Engine (Upload, Index, and Instant Mathematical Scan).
* **Phase 2 (Post-MVP):** Student Proposal Workflows, Semantic Idea Search, and Advanced UI Analytics.

---

## 2. Phase 1 (MVP): Plagiarism Engine Architecture
To balance massive scale (tens of thousands of projects) with state-of-the-art semantic accuracy, the engine utilizes a **Two-Phase Hybrid Architecture**.

### 2.1. Global Instant Scan (O(1) Time Complexity)
* **Algorithm:** Stanford's **Winnowing** Mathematical Fingerprinting.
* **Storage:** Raw project files are compressed using `zlib` in PostgreSQL. Fingerprints are indexed in a centralized `fingerprint_index` table.
* **Execution:** Calculates the Jaccard Overlap Coefficient mathematically.
* **Speed:** ~50-100 milliseconds per global scan.

### 2.2. Deep AI Semantic Analysis (On-Demand)
* **Execution:** Neural Networks operate at O(N²) complexity. To prevent server crashes, AI models are only triggered **on-demand** on specifically flagged file pairs via the UI.
* **Code Model:** `microsoft/unixcoder-base` (Utilizes Abstract Syntax Trees and comments).
* **Text/Document Model:** `BAAI/bge-m3` (Multilingual embedding model for Arabic/English paraphrase detection).

---

## 3. Phase 2 (Post-MVP): Workflows & Advanced Features
Once Phase 1 is stable, the following features from the original requirements document will be implemented:

### 3.1. Student "Idea" Semantic Search
* **Use Case:** Students search their proposed project idea/abstract to ensure it hasn't been done by another university.
* **Architecture:** Uses PostgreSQL's **`pgvector`** extension combined with local **`BAAI/bge-m3`** embeddings.
* **Workflow:** Instead of exact keyword matching, it returns projects sorted by cosine similarity to the student's abstract.

### 3.2. Faculty Proposal Approval Workflow
* **Use Case:** Department Heads review student proposals submitted via the platform.
* **Workflow:** A dedicated dashboard for faculty to `Approve` or `Reject` project titles before students begin work.

### 3.3. Side-by-Side Diff Highlighting
* **Use Case:** Advanced UI visualization for Plagiarism Reports.
* **Workflow:** When viewing a flagged match, the UI will render a split-pane view highlighting the exact stolen sentences/code blocks in red/green (similar to GitHub PR diffs).

---

## 4. Academic Defense & Benchmark References
For graduation defense, the system architecture is justified by the following benchmarked standards:
1. **Winnowing (Phase 1):** *Schleimer, S., Wilkerson, D. S., & Aiken, A. (2003).* The algorithm underlying Stanford's MOSS.
2. **UniXcoder (Phase 2 - Code):** *Guo et al. (2022).* SOTA on CodeXGLUE benchmark for semantic clone detection.
3. **BGE-M3 (Phase 2 - Text/Search):** *Chen et al. (2024).* Dominates the MTEB for multilingual semantic text similarity.
4. **Architectural Justification:** Applying O(1) mathematical indexes for global scale, layering O(N²) Neural Networks for targeted deep scans, and using `pgvector` for semantic abstract matching demonstrates senior-level system design.

---

## 5. Frontend Consolidation Strategy (Option A)
The frontend UI will be consolidated entirely inside the `plagiarism_engine_scan/frontend` directory to ensure a clean, bug-free environment. 

### Decoupled Pages Roadmap
* **Phase 1 Pages:**
  1. **Project Intake (`/`)**: Upload ZIPs or clone Git repositories.
  2. **Plagiarism Scanner (`/scan`)**: Instant mathematical scan with Phase 2 "Deep Scan" buttons.
  3. **Dashboard (`/dashboard`)**: High-level metrics and system health.
  4. **Projects (`/projects`)**: View/filter indexed projects.
  5. **Teams (`/teams`)**: Grouping 1 to N students by "رقم قيد".
  6. **Users (`/users`)**: Admin page for staff.
  7. **Settings (`/settings`)**: Global configurations.
* **Phase 2 Pages:**
  8. **Idea Search (`/idea-search`)**: Student-facing semantic abstract search.
  9. **Proposals (`/proposals`)**: Faculty approval/rejection dashboard.
  10. **Institutions (`/institutions`)**: Admin UI to manage Universities and Departments.

---

## 6. Database Entities (Expanded for Phase 1 & 2)
### MVP Entities:
* **Users:** `id`, `name`, `email`, `role`, `college_id`
* **Students:** `id`, `enrollment_number` (رقم قيد), `name`, `college_id`, `team_id`
* **Teams:** `id`, `name`, `college_id`
* **Project_Files:** `id`, `project_id`, `relative_path`, `file_type`, `content` (zlib)
* **Fingerprint_Index:** `fingerprint_hash`, `project_id`, `file_path`
* **Scan_Reports:** `id`, `project_id`, `overall_similarity`, `verdict`

### Phase 2 Expanded Entities:
* **Projects (Expanded):** `id`, `title`, `abstract`, `team_id`, `department_id`, `year`, `university_id`, `status` (Pending/Approved)
* **Abstract_Vectors:** `project_id`, `embedding` (vector type powered by pgvector)
* **Universities:** `id`, `name`
* **Departments:** `id`, `name`, `university_id`

---

## 7. Core Development Rules
1. **MVP First:** Phase 2 features (pgvector, Diff UI, Proposals) must not be started until Phase 1 (Engine + Base UI) is 100% stable.
2. **UI Separation:** Scanning, Intake, and Management must remain logically separated.
3. **Environment:** Always use `cmd /c` or `powershell -Command` with single quotes when executing shell commands.
