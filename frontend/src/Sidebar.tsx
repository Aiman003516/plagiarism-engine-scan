/**
 * Sidebar — responsive navigation rail for the authenticated app shell.
 * Rendered only from <AppLayout />, so public auth pages (/login, /register)
 * never show application chrome.
 */

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
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
  Shield,
  LogOut,
} from "lucide-react";

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

interface NavItem {
  to: string;
  label: string;
  icon: any;
  allowedRoles: string[];
}

const navItems: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/", label: "Project Intake", icon: UploadCloud, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/scan", label: "Plagiarism Scanner", icon: Search, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/projects", label: "Projects & AI Search", icon: FolderOpen, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/teams", label: "Team Management", icon: Users, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/users", label: "User Management", icon: UserCog, allowedRoles: ["ministry_admin", "university_admin", "college_admin"] },
  { to: "/settings", label: "Settings", icon: Settings, allowedRoles: ["ministry_admin", "university_admin"] },
];

import { useScanStore } from "./lib/scanStore";

function Sidebar() {
  const location = useLocation();
  const [isDark, toggleDarkMode] = useDarkMode();
  const isScanning = useScanStore((s) => s.isScanning);
  const scanSource = useScanStore((s) => s.scanSource);
  const user = (() => {
    try {
      const u = localStorage.getItem("user_data");
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  })();

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
        {navItems
          .filter((item) => item.allowedRoles.includes(user?.role || "student"))
          .map(({ to, label, icon: Icon }) => {
            const displayLabel = (to === "/teams" && user?.role === "student") ? "My Team" : label;
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
              <span className="hidden md:inline">{displayLabel}</span>
              {isScanning && ((to === "/" && scanSource === "intake") || (to === "/scan" && scanSource === "scanner")) && (
                <span className="ml-auto hidden md:flex h-2 w-2 relative" title="Scan actively processing">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              )}
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

      {/* User profile info */}
      {user && (
        <div className="hidden md:flex flex-col px-4 py-2 border-t border-border shrink-0 text-xs">
          <span className="font-semibold text-text-main truncate">{user.name || user.email}</span>
          <span className="text-text-muted capitalize">{user.role ? user.role.replace(/_/g, " ") : "Authenticated"}</span>
        </div>
      )}

      {/* Logout */}
      <div className="p-2 md:p-4 border-t border-border shrink-0">
        <button
          onClick={() => {
            localStorage.removeItem("auth_token");
            // Also drop the cached profile so no PII lingers on shared machines
            // (mirrors the 401 handler in lib/api.ts).
            localStorage.removeItem("user_data");
            window.location.href = "/login";
          }}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium text-danger hover:bg-danger/10 transition-colors"
        >
          <LogOut className="w-5 h-5" /> <span className="hidden md:inline">Log Out</span>
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;
