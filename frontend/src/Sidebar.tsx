/**
 * Sidebar — responsive navigation rail for the authenticated app shell.
 * Rendered only from <AppLayout />, so public auth pages (/login, /register)
 * never show application chrome.
 */

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { clearAllSessionCaches } from "./lib/api";
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
  Globe,
} from "lucide-react";
import { useScanStore } from "./lib/scanStore";
import { useDarkMode } from "./lib/useTheme";

interface NavItem {
  to: string;
  labelKey: string;
  icon: any;
  allowedRoles: string[];
}

const navItems: NavItem[] = [
  { to: "/dashboard", labelKey: "dashboard", icon: LayoutDashboard, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/", labelKey: "project_intake", icon: UploadCloud, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/scan", labelKey: "plagiarism", icon: Search, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty"] },
  { to: "/projects", labelKey: "projects_search", icon: FolderOpen, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/teams", labelKey: "teams", icon: Users, allowedRoles: ["ministry_admin", "university_admin", "college_admin", "faculty", "student"] },
  { to: "/users", labelKey: "user_management", icon: UserCog, allowedRoles: ["ministry_admin", "university_admin", "college_admin"] },
  { to: "/settings", labelKey: "settings", icon: Settings, allowedRoles: ["ministry_admin", "university_admin"] },
];

function Sidebar() {
  const { t, i18n } = useTranslation();
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

  const toggleLanguage = () => {
    const next = i18n.language === "ar" ? "en" : "ar";
    i18n.changeLanguage(next);
  };

  return (
    <aside className="fixed md:static inset-y-0 start-0 z-40 flex flex-col w-16 md:w-64 bg-card border-e border-border transition-all duration-300 print:hidden select-none">
      {/* Logo / Brand Lockup */}
      <div className="flex items-center justify-center md:justify-start h-16 px-0 md:px-4 border-b border-border shrink-0">
        <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0 shadow-sm">
          <Shield className="w-5 h-5" />
        </div>
        <div className="hidden md:flex flex-col ms-2.5 min-w-0">
          <span className="font-extrabold text-base text-primary tracking-tight truncate leading-tight flex items-center gap-1.5">
            نزاهة <span className="text-xs font-semibold opacity-60">| NAZAHA</span>
          </span>
          <span className="text-[10px] text-text-muted font-medium truncate">
            {i18n.language === "ar" ? "المنصة الوطنية للنزاهة الأكاديمية" : "Academic Integrity Platform"}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 md:px-3 space-y-1">
        {navItems
          .filter((item) => item.allowedRoles.includes(user?.role || "student"))
          .map(({ to, labelKey, icon: Icon }) => {
            const displayLabel = (to === "/teams" && user?.role === "student") ? (t("my_team") || "My Team") : (t(labelKey) || labelKey);
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
                title={displayLabel}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="hidden md:inline truncate">{displayLabel}</span>
                {isScanning && ((to === "/" && scanSource === "intake") || (to === "/scan" && scanSource === "scanner")) && (
                  <span className="ms-auto hidden md:flex h-2 w-2 relative" title="Scan actively processing">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                )}
              </Link>
            );
          })}
      </nav>

      {/* Bottom Controls / Footer */}
      <div className="p-2 md:p-3 border-t border-border shrink-0 space-y-2">
        {/* Dark Mode & 1-Click Language Switcher Row */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggleDarkMode}
            className="flex items-center justify-center md:justify-start gap-2 flex-1 px-2.5 py-2 rounded-xl text-xs font-medium text-text-muted hover:bg-text-muted/10 hover:text-text-main transition-colors"
            title={isDark ? (t("light_mode") || "Light Mode") : (t("dark_mode") || "Dark Mode")}
            aria-label="Toggle dark mode"
          >
            {isDark ? (
              <Sun className="w-4 h-4 flex-shrink-0 text-amber-500" />
            ) : (
              <Moon className="w-4 h-4 flex-shrink-0 text-indigo-400" />
            )}
            <span className="hidden md:inline truncate">
              {isDark ? (t("light_mode") || "Light Mode") : (t("dark_mode") || "Dark Mode")}
            </span>
          </button>

          <button
            type="button"
            onClick={toggleLanguage}
            className="flex items-center justify-center p-2 rounded-xl text-primary hover:bg-text-muted/10 hover:text-text-main transition-colors border border-border/70"
            title={i18n.language === "ar" ? "Switch to English" : "التبديل إلى العربية"}
            aria-label="Toggle language"
          >
            <Globe className="w-4 h-4 flex-shrink-0" />
          </button>
        </div>

        {/* User profile info badge */}
        {user && (
          <div className="hidden md:flex flex-col px-2.5 py-1.5 rounded-lg bg-surface/50 border border-border/50 text-xs">
            <span className="font-semibold text-text-main truncate">{user.name || user.email}</span>
            <span className="text-text-muted text-[11px] truncate">
              {user.role ? (t(`role_${user.role}`) || user.role.replace(/_/g, " ")) : (t("authenticated") || "Authenticated")}
            </span>
          </div>
        )}

        {/* Log Out */}
        <button
          onClick={() => {
            clearAllSessionCaches();
            try {
              useScanStore.getState().resetAll();
            } catch {}
            window.location.href = "/login";
          }}
          className="flex items-center justify-center md:justify-start gap-2.5 w-full px-2.5 py-2 rounded-xl text-xs font-semibold text-danger hover:bg-danger/10 transition-colors"
          title={t("logout") || "Log Out"}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          <span className="hidden md:inline">{t("logout") || "Log Out"}</span>
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;
