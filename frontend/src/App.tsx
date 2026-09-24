/**
 * Ministry Plagiarism Engine — React App Entry
 * Responsive sidebar navigation for all Phase 1 pages.
 */

import React, { Suspense, useEffect, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useLocation,
} from "react-router-dom";
import { Toaster } from "react-hot-toast";
import {
  UploadCloud,
  Search,
  LayoutDashboard,
  FolderOpen,
  Users,
  UserCog,
  Settings,
  Moon,
  Sun,
  RefreshCw,
  Shield,
} from "lucide-react";

// --- Phase 1 pages: lazy imports ---
// Existing pages
const ProjectIntake = React.lazy(() =>
  import("./pages/Plagiarism").then((module) => ({
    default: module.Plagiarism,
  }))
);

const PlagiarismScanner = React.lazy(() =>
  import("./pages/PlagiarismAnalysis").then((module) => ({
    default: module.PlagiarismAnalysis,
  }))
);

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const Projects = React.lazy(() => import("./pages/Projects"));
const Teams = React.lazy(() => import("./pages/Teams"));
const UsersPage = React.lazy(() => import("./pages/Users"));
const SettingsPage = React.lazy(() => import("./pages/Settings"));
const LoginPage = React.lazy(() => import("./pages/Login"));
const RegisterPage = React.lazy(() => import("./pages/Register"));
const NotFoundPage = React.lazy(() => import("./pages/NotFound"));

// --- Shared components ---

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-full bg-background">
      <RefreshCw className="w-8 h-8 animate-spin text-accent" />
    </div>
  );
}

function useDarkMode() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const stored = localStorage.getItem("theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    if (isDark) document.documentElement.classList.add("dark");
    else document.documentElement.classList.remove("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
  }, [isDark]);

  return [isDark, () => setIsDark((d) => !d)] as const;
}

const navItems = [
  { to: "/", label: "Project Intake", icon: UploadCloud },
  { to: "/scan", label: "Plagiarism Scanner", icon: Search },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FolderOpen },
  { to: "/teams", label: "Team Management", icon: Users },
  { to: "/users", label: "User Management", icon: UserCog },
  { to: "/settings", label: "Settings", icon: Settings },
];

function Sidebar() {
  const location = useLocation();
  const [isDark, toggleDarkMode] = useDarkMode();

  return (
    <aside className="fixed md:static inset-y-0 left-0 z-40 flex flex-col w-16 md:w-64 bg-card border-r border-border transition-all duration-300 print:hidden">
      {/* Logo */}
      <div className="flex items-center justify-center md:justify-start h-16 px-0 md:px-5 border-b border-border shrink-0">
        <Shield className="w-7 h-7 text-primary flex-shrink-0" />
        <span className="hidden md:block ml-3 font-bold text-lg text-primary tracking-tight">
          Ministry System
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 md:px-3 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => {
          const isActive = location.pathname === to;
          return (
            <Link
              key={to}
              to={to}
              className={`flex items-center justify-center md:justify-start gap-0 md:gap-3 px-2 md:px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? "bg-accent text-accent-text shadow-sm"
                  : "text-text-muted hover:bg-text-muted/10 hover:text-text-main"
              }`}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span className="hidden md:inline">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Dark mode toggle */}
      <div className="p-2 md:p-4 border-t border-border shrink-0">
        <button
          type="button"
          onClick={toggleDarkMode}
          className="flex items-center justify-center md:justify-start gap-0 md:gap-3 w-full px-2 md:px-3 py-2.5 rounded-xl text-sm font-medium text-text-muted hover:bg-text-muted/10 hover:text-text-main transition-colors"
          aria-label="Toggle dark mode"
        >
          {isDark ? (
            <Sun className="w-5 h-5 flex-shrink-0" />
          ) : (
            <Moon className="w-5 h-5 flex-shrink-0" />
          )}
          <span className="hidden md:inline">
            {isDark ? "Light Mode" : "Dark Mode"}
          </span>
        </button>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: "rgb(30 41 59)",
            color: "#f8fafc",
            border: "1px solid rgba(148,163,184,0.15)",
          },
        }}
      />
      <div className="h-full w-full flex overflow-hidden bg-background text-text-main">
        <Sidebar />
        <div className="flex-1 flex flex-col ml-16 md:ml-0 overflow-hidden">
          <Suspense fallback={<LoadingSpinner />}>
            <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
              <div className="max-w-7xl mx-auto">
                <Routes>
                  <Route path="/" element={<ProjectIntake />} />
                  <Route path="/scan" element={<PlagiarismScanner />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/projects" element={<Projects />} />
                  <Route path="/teams" element={<Teams />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </div>
            </main>
          </Suspense>
        </div>
      </div>
    </BrowserRouter>
  );
}
