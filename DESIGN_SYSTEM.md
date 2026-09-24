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
