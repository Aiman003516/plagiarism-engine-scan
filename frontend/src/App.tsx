/**
 * Ministry Plagiarism Engine — React App Entry
 * Responsive sidebar navigation for all Phase 1 pages.
 */

import React, { Suspense } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { RefreshCw } from "lucide-react";
import ErrorBoundary from "./components/ErrorBoundary";
import Sidebar from "./Sidebar";

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
const ForceChangePasswordPage = React.lazy(
  () => import("./pages/ForceChangePassword")
);

// --- Route guard: requires a valid auth token in localStorage ---

function ProtectedRoute() {
  const token = localStorage.getItem("auth_token");
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

// --- Shared components ---

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-full bg-background">
      <RefreshCw className="w-8 h-8 animate-spin text-accent" />
    </div>
  );
}

/**
 * AppLayout — authenticated shell: sidebar + scrollable content region.
 * Mounted as a pathless layout route *inside* ProtectedRoute so the sidebar
 * never renders on public pages (/login, /register, 404).
 */
function AppLayout() {
  return (
    <div className="h-full w-full flex overflow-hidden bg-background text-text-main">
      <Sidebar />
      <div className="flex-1 flex flex-col ml-16 md:ml-0 overflow-hidden">
        <ErrorBoundary>
          <Suspense fallback={<LoadingSpinner />}>
            <main className="flex-1 overflow-y-auto p-4 md:p-8">
              <div className="max-w-7xl mx-auto">
                <Outlet />
              </div>
            </main>
          </Suspense>
        </ErrorBoundary>
      </div>
    </div>
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
      {/* Outer boundary: /login, /register and the 404 page are lazy too and
          render outside AppLayout's Suspense, so they need their own fallback. */}
      <ErrorBoundary>
        <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            {/* Protected application routes — require auth_token + app chrome */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<ProjectIntake />} />
                <Route path="/scan" element={<PlagiarismScanner />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/teams" element={<Teams />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route
                  path="/force-change-password"
                  element={<ForceChangePasswordPage />}
                />
              </Route>
            </Route>
            {/* Public routes — no sidebar chrome */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
