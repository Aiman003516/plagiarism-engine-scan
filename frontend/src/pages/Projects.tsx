import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  FolderOpen,
  RefreshCw,
  Search,
  Trash2,
  FileText,
  X,
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { plagiarismApi, ProjectSummary, ProjectFile } from "../lib/api";

export default function Projects() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filesProject, setFilesProject] = useState<{
    project: ProjectSummary;
    files: ProjectFile[];
  } | null>(null);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [page, setPage] = useState(1);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const PAGE_SIZE = 20;

  // Cached login profile (written by Login.tsx as "user_data"). Drives both the
  // student visibility filter and the faculty "Approve" action below.
  const user = useMemo<{ id?: string; role?: string } | null>(() => {
    const userStr = localStorage.getItem("user_data") || localStorage.getItem("user");
    if (!userStr) return null;
    try {
      return JSON.parse(userStr);
    } catch {
      return null;
    }
  }, []);
  const isStudent = user?.role === "student";

  const load = async () => {
    setLoading(true);
    try {
      const res = await plagiarismApi.getProjects();
      setProjects(res.projects || []);
    } catch (e: any) {
      toast.error(e?.message || "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const viewFiles = async (project: ProjectSummary) => {
    setLoadingFiles(true);
    try {
      const res = await plagiarismApi.getProjectFiles(project.id);
      setFilesProject({ project, files: res.files || [] });
    } catch (e: any) {
      toast.error(e?.message || "Failed to load files");
    } finally {
      setLoadingFiles(false);
    }
  };

  const deleteProject = async (project: ProjectSummary) => {
    if (!window.confirm(t("confirm_delete"))) return;
    try {
      await plagiarismApi.deleteProject(project.id);
      toast.success(t("delete_success"));
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to delete");
    }
  };

  const approveProject = async (project: ProjectSummary) => {
    setApprovingId(project.id);
    try {
      await plagiarismApi.approveProject(project.id);
      toast.success(t("approve_success"));
      load();
    } catch (e: any) {
      toast.error(e?.message || t("approve_failed"));
    } finally {
      setApprovingId(null);
    }
  };

  const filtered = projects.filter((p) => {
    // Students only ever see their own submissions; staff/admins see everything.
    if (isStudent && p.student_id !== user?.id) return false;

    return (
      !search.trim() ||
      ((p.name || "").toLowerCase().includes(search.toLowerCase()) ||
        (p.title || "").toLowerCase().includes(search.toLowerCase()) ||
        (p.university || "").toLowerCase().includes(search.toLowerCase()))
    );
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      <header className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-text-main">
            {t("projects_title")}
          </h1>
          <p className="text-text-muted mt-1">{t("projects_subtitle")}</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field w-full pl-9"
            placeholder={t("search_projects")}
          />
        </div>
      </header>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh] text-text-muted">
          <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-panel p-10 text-center text-text-muted">
          <FolderOpen className="w-8 h-8 mx-auto mb-3 opacity-50" />
          {t("no_projects_found")}
        </div>
      ) : (
        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur">
                <tr className="text-left text-text-muted border-b border-border">
                  <th className="py-3 px-4 font-medium">{t("project")}</th>
                  <th className="py-3 px-4 font-medium">{t("university")}</th>
                  <th className="py-3 px-4 font-medium">{t("department")}</th>
                  <th className="py-3 px-4 font-medium">{t("year")}</th>
                  <th className="py-3 px-4 font-medium">{t("status")}</th>
                  <th className="py-3 px-4 font-medium text-right">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {paged.map((p) => (
                  <tr key={p.id} className="hover:bg-surface/50 transition-colors border-b border-border/40 last:border-0">
                    <td className="py-3 px-4">
                      <div className="font-medium text-text-main">{p.title || p.name}</div>
                      {p.abstract && (
                        <div className="text-xs text-text-muted truncate max-w-[280px]">
                          {p.abstract}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-text-muted">{p.university || "—"}</td>
                    <td className="py-3 px-4 text-text-muted">{p.department || "—"}</td>
                    <td className="py-3 px-4 text-text-muted">{p.year ?? "—"}</td>
                    <td className="py-3 px-4">
                      <span
                        className={
                          p.status === "pending"
                            ? "bg-warning/20 text-warning px-2 py-1 rounded text-xs"
                            : "bg-success/20 text-success px-2 py-1 rounded text-xs"
                        }
                      >
                        {p.status?.toUpperCase() || "APPROVED"}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center justify-end gap-2">
                        {p.status === "pending" && !isStudent && (
                          <button
                            onClick={() => approveProject(p)}
                            disabled={approvingId === p.id}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-success/20 text-success hover:bg-success/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title={t("approve")}
                          >
                            {approvingId === p.id ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            )}
                            {t("approve")}
                          </button>
                        )}
                        <button
                          onClick={() => viewFiles(p)}
                          className="p-1.5 rounded-lg text-text-muted hover:bg-text-muted/10 hover:text-text-main transition-colors"
                          title={t("view_files")}
                        >
                          <FileText className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => deleteProject(p)}
                          className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
                          title={t("delete")}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <span className="text-xs text-text-muted">
                {t("showing_page")} {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} {t("of_pages")} {filtered.length}
              </span>
              <div className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-2.5 py-1 rounded-lg text-xs text-text-muted border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t("prev_page")}
                </button>
                <span className="text-xs text-text-muted">{page} / {totalPages}</span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="px-2.5 py-1 rounded-lg text-xs text-text-muted border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {t("next_page")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      {filesProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="glass-panel w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h2 className="text-lg font-semibold text-text-main">
                {filesProject.project.title || filesProject.project.name} — {t("view_files")}
              </h2>
              <button
                onClick={() => setFilesProject(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-text-muted/10"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 overflow-y-auto flex-1">
              {loadingFiles ? (
                <div className="flex justify-center py-10 text-text-muted">
                  <RefreshCw className="w-5 h-5 animate-spin text-accent" />
                </div>
              ) : filesProject.files.length === 0 ? (
                <p className="text-text-muted text-center py-10">{t("no_files_staged")}</p>
              ) : (
                <ul className="space-y-2">
                  {filesProject.files.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface/50 border border-border/50"
                    >
                      <FileText className="w-4 h-4 text-text-muted flex-shrink-0" />
                      <span className="font-mono text-xs text-text-main truncate">
                        {f.relative_path}
                      </span>
                      <span className="ml-auto text-xs text-text-muted flex-shrink-0">
                        {f.file_type}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
