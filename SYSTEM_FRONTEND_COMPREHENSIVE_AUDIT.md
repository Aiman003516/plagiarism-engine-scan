# Comprehensive Frontend System Architecture & Technical Audit

> **System**: Web User Interface for Multi-Language Code & Academic Text Plagiarism Detection  
> **Location**: `C:\Users\Ayman\Downloads\plagiarism_engine_scan\frontend`  
> **Auditor**: Master Systems Analyst & Architecture Team  
> **Target Runtime**: React 19 / Vite 6 / TypeScript 5.8 / Tailwind CSS v4 / Zustand  

---

## 1. Executive Summary & UI/UX Design System

The frontend is a single-page application (SPA) engineered for high-performance file processing, real-time telemetry streaming, and institutional workflow management. It provides an enterprise glassmorphism aesthetic with full bilingual support (Arabic and English), responsive light/dark themes, and role-based interface gating.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      React 19 Root (<App />)                           │
│                      Hash / Browser Router                             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         │                                                     │
┌────────▼──────────────┐                             ┌────────▼──────────────┐
│  Public Auth Routes   │                             │ Protected App Shell   │
│  • /login             │                             │ (<AppLayout />)       │
│  • /register          │                             └──────────┬────────────┘
│  • /change-password   │                                        │
└───────────────────────┘                    ┌───────────────────┴───────────────────┐
                                             │                                       │
                                   ┌─────────▼────────┐                    ┌─────────▼────────┐
                                   │ Responsive Nav   │                    │ <RoleGuard />    │
                                   │ (<Sidebar />)    │                    │ Access Control   │
                                   └──────────────────┘                    └─────────┬────────┘
                                                                                     │
         ┌───────────────────┬───────────────────────┼───────────────────────┬───────┴───────────┐
         │                   │                       │                       │                   │
┌────────▼─────────┐ ┌───────▼──────────┐ ┌──────────▼────────┐ ┌────────────▼───────┐ ┌─────────▼────────┐
│ Project Intake   │ │ Plagiarism       │ │ Direct Pairwise   │ │ Catalog & Search   │ │ Administration  │
│ • Dropzone       │ │ Scanner          │ │ Comparison        │ │ • Projects Catalog │ │ • Teams         │
│ • Git Clone      │ │ • Corpus Scan    │ │ • Dual Drag/Drop  │ │ • Student Proposal │ │ • Users & Roster│
│ • SSE Terminal   │ │ • Deep AI Matrix │ │ • Side-by-Side    │ │ • Supervisor Review│ │ • Settings      │
└──────────────────┘ └──────────────────┘ └───────────────────┘ └────────────────────┘ └──────────────────┘
```

### Core Frontend Stack
- **Library & Framework**: React `^19.0.1` with React DOM `^19.0.1`.
- **Bundler & Tooling**: Vite `^6.2.3` with `@vitejs/plugin-react` `^5.0.4`.
- **Type Safety**: TypeScript `~5.8.2` (strict mode enabled).
- **Styling**: Tailwind CSS `^4.1.14` with `@tailwindcss/vite` and `tailwind-merge` `^3.6.0`.
- **Motion & Animations**: Framer Motion `^12.42.2`.
- **State Management**: Zustand `^5.0.15` with selective `localStorage` persistence.
- **Internationalization (i18n)**: `i18next` `^26.3.6` and `react-i18next` `^17.0.11` with dynamic RTL/LTR direction switching.
- **Data Visualization**: Recharts `^3.10.1`.
- **Icons**: Lucide React `^0.546.0`.
- **Notifications**: React Hot Toast `^2.6.0`.
- **Document Export**: `jspdf` `^4.2.1` and `html2canvas` `^1.4.1`.

---

## 2. Component Hierarchy & Page Inventory

```
frontend/src/
├── App.tsx                          # Router configuration and layout definitions
├── main.tsx                         # Bootstrap entry point (fonts, i18n, CSS)
├── Sidebar.tsx                      # Navigation rail, active route highlighting, logout cleanup
├── index.css                        # Glassmorphism utilities, CSS custom properties, scrollbars
├── vite-env.d.ts                    # Vite client types
│
├── components/                      # Reusable UI widgets
│   ├── DiffViewer.tsx               # Synchronized dual-pane diff comparison viewer
│   ├── RoleGuard.tsx                # Role-based route protection and redirection
│   └── ErrorBoundary.tsx            # Global React error boundary for crash containment
│
├── lib/                             # Core utilities and client services
│   ├── api.ts                       # Typed fetch client, API endpoints, 401 interceptors
│   ├── i18n.tsx                     # Translations dictionary (Arabic & English), RTL controller
│   ├── scanStore.ts                 # Central Zustand store (intake, execution, re-attach)
│   ├── useProjectsCache.ts          # Project list memory cache hook with invalidation
│   ├── useTeamsCache.ts             # Academic teams memory cache hook
│   ├── useUsersCache.ts             # User roster memory cache hook
│   └── utils.ts                     # Classname merging and formatting helpers
│
└── pages/                           # Application route views
    ├── Dashboard.tsx                # Overview statistics, charts, scan distribution
    ├── PlagiarismAnalysis.tsx       # Direct pairwise file comparison (Drag & Drop File A / B)
    ├── Projects.tsx                 # Academic project catalog, proposals, search, reviews
    ├── Teams.tsx                    # Student teams, member management, token granting
    ├── Users.tsx                    # Multi-tier user administration and bulk CSV/Excel import
    ├── Settings.tsx                 # Language, theme, and threshold controls
    ├── Login.tsx                    # Unified email and student ID login screen
    ├── Register.tsx                 # Self-registration screen
    ├── ForceChangePassword.tsx      # Mandatory first-login password update screen
    ├── NotFound.tsx                 # 404 handler
    └── plagiarism/                  # Core scanning modules
        ├── index.tsx                # Intake & Scanner unified controller
        ├── UploadSection.tsx        # File dropzone, directory traversal, project name auto-detector
        ├── ScanProgress.tsx         # Real-time execution stream terminal, clear button, timer
        ├── GitScanSection.tsx       # Remote Git shallow cloning interface
        ├── StagedFilesExplorer.tsx  # Pre-scan staged files categorized breakdown
        ├── SummaryCards.tsx         # Plagiarism score cards (Winnowing, Semantic, Fusion)
        ├── DeepScanPanel.tsx        # Exhaustive N×M semantic comparison matrix
        ├── ComparisonsTable.tsx     # High-risk match table with jump-to-diff links
        ├── ScanHistoryModal.tsx     # Historical scan reports viewer
        ├── fileConstants.ts         # Binary extensions and client exclusion patterns
        └── hooks/
            └── useScanStream.ts     # SSE EventSource streaming lifecycle hook
```

---

## 3. Client-Side Traversal & Bloatware Filtration Engine

One of the most critical performance optimizations in the system is client-side directory traversal and pre-filtering in [UploadSection.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/pages/plagiarism/UploadSection.tsx).

### 3.1 Non-Blocking Directory Traversal
When a user drops or selects an entire directory (which may contain 10,000+ files):
1. The browser's `webkitRelativePath` handles folder hierarchy preservation.
2. Traversal is processed in chunks of **500 files** per tick.
3. Between chunks, execution yields to the browser event loop using `await new Promise(r => setTimeout(r, 0))` to prevent UI freezing or dropped frames.

### 3.2 Pre-Ingestion Bloatware Filtration
Before files are loaded into browser RAM or transmitted to the backend, they are inspected against an exclusion policy:
- **Dependency & Build Directories**: `node_modules`, `.git`, `venv`, `.venv`, `env`, `dist`, `build`, `target`, `__pycache__`, `.idea`, `.vscode`, `.next`, `.nuxt`.
- **Binary Assets**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.webp`, `.mp4`, `.mp3`, `.wav`, `.zip`, `.tar`, `.gz`, `.exe`, `.dll`, `.class`, `.jar`, `.pyc`, `.pt`, `.onnx`, `.tflite`.
- **Manifests & Lockfiles**: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`, `poetry.lock`, `Cargo.lock`, `composer.lock`.
- **Tabular & Log Bloat**: `.log`, `.csv`, `.tsv`, `.jsonl`.

### 3.3 Dynamic Project Name Inference
The redundant manual project name text input was eliminated. The system automatically infers the project name:
1. Root directory name of dropped folder (e.g. `Attendance_App/` $\rightarrow$ `Attendance_App`).
2. Stem of dropped ZIP archive (e.g. `Robotics_V2.zip` $\rightarrow$ `Robotics_V2`).
3. Single file stem (e.g. `main_solver.py` $\rightarrow$ `main_solver`).
Users wishing to attach formal institutional titles (e.g. *"Autonomous UAV SLAM Navigation"*) expand the Academic & Project Metadata drawer.

---

## 4. State Management & Lifecycle Architecture (`scanStore.ts`)

The central Zustand store is partitioned into three functional state groups with selective persistence:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Zustand scanStore                               │
│                                                                        │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ Group A: Pre-Scan       │  │ Group B: Scan Execution             │  │
│  │ • uploadedFiles         │  │ • isScanning / scanSource           │  │
│  │ • projectName           │  │ • scanLogs (capped at 400 lines)    │  │
│  │ • bloatFilteredCount    │  │ • scanResult / scanError            │  │
│  │ • isProcessingFiles     │  │ • scanDuration / abortController    │  │
│  └─────────────────────────┘  └─────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Group C: Reconnect Capability                                    │  │
│  │ • activeProjectId / streamToken (UUID4 capability token)         │  │
│  │ • scanStartedAt / streamLogCount (resume cursor)                 │  │
│  │ • deepScanResultsCache                                           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

### Selective Persistence & Memory Hygiene
- **Storage Key**: `plagiarism-scan-storage` in browser `localStorage`.
- **Log Buffer Cap**: `scanLogs` is sliced to the last **400 lines** before persistence, guaranteeing storage remains within browser 5 MB limits.
- **Session Reset on Staging**: When new files are staged, `resetScan()` immediately purges old execution terminal lines and past results.
- **Total Wipeout on Logout**: In [Sidebar.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/Sidebar.tsx), logging out executes:
  ```ts
  localStorage.removeItem("auth_token");
  localStorage.removeItem("user_data");
  localStorage.removeItem("plagiarism-scan-storage");
  useScanStore.getState().resetAll();
  ```
  ensuring no residual student records or execution streams leak across users.

---

## 5. Real-Time Streaming & Re-Attach Architecture

The execution terminal in [ScanProgress.tsx](file:///C:/Users/Ayman/Downloads/plagiarism_engine_scan/frontend/src/pages/plagiarism/ScanProgress.tsx) delivers live progress via Server-Sent Events (SSE):

```
Browser Client                                                    Backend Server
      │                                                                 │
      │ 1. POST /api/plagiarism/upload-scan-stream (FormData)          │
      ├────────────────────────────────────────────────────────────────►│
      │    First frame: {"type": "session", "stream_token": "a1b2..."}  │
      │◄────────────────────────────────────────────────────────────────┤
      │    Frame 2: {"type": "log", "text": "Extracting files..."}     │
      │◄────────────────────────────────────────────────────────────────┤
   [User Navigates Away or Refreshes Page]                              │
      │                                                                 │
      │ 2. Rehydrate state: reads activeProjectId & streamToken         │
      │    GET /api/plagiarism/scan-stream/{id}?token=...&after=52      │
      ├────────────────────────────────────────────────────────────────►│
      │    Replays missed events from backlog cursor                     │
      │◄────────────────────────────────────────────────────────────────┤
      │    Continues live streaming until completion                    │
      │◄────────────────────────────────────────────────────────────────┤
```

### Terminal UI Controls
- **Live Elapsed Timer**: Formats runtime as `MM:SS` dynamically.
- **Auto-Scroll Toggle**: Automatically pins the terminal view to the latest incoming log event, with option to pause for inspection.
- **Clear Terminal Button**: Added a dedicated `<Trash2>` button allowing users to wipe terminal output at any time.
- **Abort Control**: Calls `abortController.abort()` to terminate in-flight HTTP requests and notifies the server.
- **Export Capabilities**: One-click clipboard copy and text log file download (`plagiarism-scan-log-<timestamp>.txt`).

---

## 6. Internationalization (i18n) & Accessibility

- **Engine**: `react-i18next` with modular Arabic and English resource files.
- **Dynamic RTL/LTR Switching**: Switching language to Arabic dynamically sets `document.documentElement.dir = 'rtl'` and `lang = 'ar'`, flipping margins, paddings, icon alignments, and table orientations.
- **Typography**: Uses **Plus Jakarta Sans** with specialized fallbacks for Arabic glyphs.
- **Design System**: Full glassmorphism support using CSS variables (`--color-surface`, `--color-border-glass`, `--color-primary`, `--color-accent`) supporting smooth transitions between light and dark modes.
