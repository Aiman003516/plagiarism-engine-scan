# Ministry Plagiarism Engine: UI/UX Design System

This document serves as the visual and structural rulebook for the frontend of the Ministry-Scale Plagiarism Engine. It defines the color palette, typography, component behaviors, and the UI/UX layout for every page defined in `BLUEPRINT.md`. 

The goal of this design system is to ensure the platform feels **academic, authoritative, premium, and highly modern**, breaking away from generic corporate dashboard templates.

---

## 1. Color Palette: "Emerald & Butter"
The system utilizes a distinctive, high-end palette based on Deep Emerald (`#013e37`) and Butter (`#ffefb3`). This creates a luxurious, trustworthy aesthetic reminiscent of top-tier academic institutions.

### Light Mode Strategy (Clean & Editorial)
* **Background (`--background`):** Warm off-white (`#faf9f5`). Avoids harsh digital white, reducing eye strain.
* **Surface/Cards (`--card`):** Pure white (`#ffffff`) with very subtle, warm borders (`#ebe6d5`).
* **Text (`--foreground`):** Deep Emerald (`#013e37`). Provides high contrast while feeling richer than generic black.
* **Primary Accents (`--primary`):** Deep Emerald backgrounds with Butter text for primary CTA buttons.
* **Badges/Highlights (`--accent`):** Butter backgrounds with Deep Emerald text for "Safe" statuses or active tabs.

### Dark Mode Strategy (Luxury Command Center)
* **Background (`--background`):** Deep Obsidian/Pine (`#061a17`). A dark undertone derived directly from the primary green, avoiding flat black.
* **Surface/Cards (`--card`):** Deep Pine (`#0c2b26`) with glowing, subtle borders (`#1a4a42`).
* **Text (`--foreground`):** Crisp Cream/White (`#f4f3ec`).
* **Primary Accents (`--primary`):** Butter (`#ffefb3`) backgrounds with Deep Emerald text. Butter pops brilliantly in dark mode, instantly drawing the eye to primary actions.

### 1.1 Semantic Status & Metric Palette (multi-color layer)
The Emerald & Butter pair owns **brand identity only**. Status and metrics use a
separate, explicit semantic palette so a screen can be read by colour alone.

Defined as raw RGB triplets in `:root` / `.dark` in `frontend/src/index.css` so
Tailwind opacity modifiers (`bg-success/10`) keep working, and surfaced as
utilities through `@theme inline reference`
(`--color-success: rgb(var(--success) / <alpha-value>)`).

| Token | Light | Dark | Meaning |
| --- | --- | --- | --- |
| `--success` | `16 185 129` (emerald-500) | `52 211 153` (emerald-400) | Safe / approved / clean / resolved |
| `--danger` | `239 68 68` (red-500) | `248 113 113` (red-400) | Flagged / destructive / error |
| `--warning` | `245 158 11` (amber-500) | `251 191 36` (amber-400) | Pending / at-risk / in progress |
| `--info` | `59 130 246` (blue-500) | `96 165 250` (blue-400) | Informational / neutral highlight |
| `--metric-purple` | `168 85 247` (purple-500) | `192 132 252` (purple-400) | Users & identities |
| `--metric-teal` | `20 184 166` (teal-500) | `45 212 191` (teal-400) | Teams & groups |

Dark mode lifts every hue to its 400-level shade — saturated 500-level colours
lose contrast against the obsidian background.

**Dashboard KPI tone map** (`TONES` in `frontend/src/pages/Dashboard.tsx`). Each
tone owns an icon badge, a hint colour and a mini progress bar; the card shell
stays neutral (`rounded-2xl`, `shadow-sm`, `border-slate-200/800`) so the hue pops:

| Metric | Tone |
| --- | --- |
| Total Projects | blue |
| Total Teams | teal |
| Total Users | purple |
| Total Files | amber |
| Safe Projects | emerald |
| Flagged Scans | red |

**Similarity gradient** (shared by `Dashboard.tsx` and `Plagiarism.tsx`):
`>= 70% -> text-red-500`, `40–69% -> text-amber-500`, `< 40% -> text-emerald-500`.

**Badge shape** for every status pill:
`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1`
plus the tone's `bg-*-500/10 text-*-500 ring-*-500/20`.

### 1.2 Button Hierarchy (strict)
One primary action per view. Use the classes from `index.css`, never ad-hoc
colour strings:

| Class | Use for |
| --- | --- |
| `.btn-primary` | The single main action of a view (Start Scan, Add Team, Save). Solid brand. |
| `.btn-secondary` | Supporting actions (View Members, Download CSV, Reset, Cancel). Outlined. |
| `.btn-danger` | Explicit destructive action with a label (Clear All, Clear Uploads). Solid red. |
| `.btn-danger-icon` | Destructive icon-only row action (Trash). Quiet red, intensifies on hover. |

Destructive actions **never** use the brand colour, and never use the faint
`bg-danger/10` ghost treatment, which used to read as decoration rather than as
a warning.


---

## 2. Typography & Core UI Rules
* **Font Family:** `Inter` or `Plus Jakarta Sans` for clean, highly legible data tables and UI elements.
* **Spacing:** Strict 8-point grid system (`p-2`, `p-4`, `p-8` in Tailwind) to ensure structural rhythm.
* **Border Radius:** `rounded-xl` (12px) or `rounded-2xl` (16px) for cards and modals to keep the UI feeling modern and approachable, avoiding harsh sharp edges.
* **Shadows/Elevation:** 
  * Light Mode: Soft, diffused shadows (`shadow-sm`, `shadow-md` with 5% opacity).
  * Dark Mode: Glow effects or inner borders instead of drop shadows.

---

## 3. Component Standards
* **Buttons:** Solid colors for Primary, outlined/ghost for Secondary. Always include a hover state (e.g., slight opacity drop or transform scaling). Include loading states (spinners) replacing icons when clicked.
* **Data Tables:** Must have sticky headers, sortable columns, and pagination. Hover effects on rows (`hover:bg-muted/50`) to help users track data across wide screens.
* **Forms:** Floating labels or clean top-aligned labels. Input fields should have clear focus rings (`focus:ring-2 focus:ring-primary/20`) for accessibility.
* **Alerts/Toasts:** Used for transient success/error messages, snapping to the bottom-right.

---

## 4. Page UI/UX Descriptions (Mapped to Blueprint)

### Phase 1 Pages (MVP)

#### 1. Project Intake (`/`)
* **UX Goal:** Frictionless data entry and uploading.
* **Layout:** Centered, focused layout. A massive, dashed-border "Drag & Drop" zone for ZIP/Git uploads. 
* **State Management:** Progress bars mapping the ingestion, extraction, and indexing phases so the user is never left wondering if the system froze.

#### 2. Plagiarism Scanner (`/scan`)
* **UX Goal:** Clarity on academic integrity and fast results.
* **Layout:**
  * Top: 4 Stat Cards (Overall Score, Verdict Badge, File Count, Speed).
  * Middle: High-contrast data table showing exact matched files.
  * *Phase 2 Upgrade:* Clicking a row expands a **Split-Pane Diff Viewer** (Side-by-Side code/text comparison) with plagiarized strings highlighted with `bg-red-500/20`.

#### 3. Dashboard (`/dashboard`)
* **UX Goal:** A "Command Center" overview for Ministry/College Admins.
* **Layout:** Grid layout using modern cards.
  * Radar charts or bar graphs showing plagiarism trends over time.
  * Top widgets for "Total Projects Indexed", "Active Teams", and "Recent Flagged Violations".

#### 4. Management Pages (`/projects`, `/teams`, `/users`)
* **UX Goal:** Bulk data management with ease.
* **Layout:** Full-width Data Tables.
  * Top bar: Global search, role-based filters (e.g., filter by College or Department), and a primary "Add New" button.
  * Table rows must feature action menus (three-dot dropdowns) for Edit/Delete/View details.

#### 5. Settings (`/settings`)
* **UX Goal:** Clean configuration.
* **Layout:** Left-aligned vertical tabs (e.g., Account, System Config, Similarity Thresholds, Theme) navigating to specific form sections on the right.

### Phase 2 Pages (Post-MVP)

#### 6. Idea Search (`/idea-search`)
* **UX Goal:** Similar to Google Scholar; heavily search-optimized.
* **Layout:** A massive, centered search bar with natural language prompting ("Describe your project idea...").
* **Results:** Card-based list view showing existing project abstracts, sorted by Semantic Similarity Score (powered by `pgvector`).

#### 7. Proposals (`/proposals`)
* **UX Goal:** A fast triage queue for Faculty.
* **Layout:** Kanban board (Pending, Approved, Rejected) OR a dense list view. Faculty can click a proposal to open a side-panel reading pane, enabling one-click approvals without losing their place in the queue.

#### 8. Institutions (`/institutions`)
* **UX Goal:** Managing the hierarchy (University -> Department).
* **Layout:** Nested list or Accordion UI, allowing Ministry admins to drill down into specific universities to manage their departments and assign head faculty members.
