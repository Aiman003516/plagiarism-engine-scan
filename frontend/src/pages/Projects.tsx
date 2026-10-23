import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  FolderOpen,
  RefreshCw,
  Search,
  Trash2,
  FileText,
  X,
  Sparkles,
  SlidersHorizontal,
  GraduationCap,
  Building2,
  Calendar,
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  Unlock,
  Lock,
  Send,
  MessageSquare,
  Clock,
  XCircle,
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  plagiarismApi,
  ProjectSummary,
  ProjectFile,
  SemanticSearchResult,
  teamsApi,
  TeamData,
} from "../lib/api";
import { useProjectsCache } from "../lib/useProjectsCache";

export default function Projects() {
  const { t } = useTranslation();
  const { projects, loading, error, refresh: load } = useProjectsCache();

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

  const [activeTab, setActiveTab] = useState<"repository" | "semantic">(isStudent ? "semantic" : "repository");

  // Repository state
  const [search, setSearch] = useState("");
  const [filesProject, setFilesProject] = useState<{
    project: ProjectSummary | { id: string; title: string; name: string };
    files: ProjectFile[];
  } | null>(null);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [page, setPage] = useState(1);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const PAGE_SIZE = 20;

  // Semantic Search state
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticThreshold, setSemanticThreshold] = useState(0.15);
  const [semanticDept, setSemanticDept] = useState("");
  const [semanticUni, setSemanticUni] = useState("");
  const [searchingSemantic, setSearchingSemantic] = useState(false);
  const [semanticResults, setSemanticResults] = useState<SemanticSearchResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [modelUsed, setModelUsed] = useState("bge-m3");

  // Student Submission & Team State
  const [studentTeam, setStudentTeam] = useState<TeamData | null>(null);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submitTitle, setSubmitTitle] = useState("");
  const [submitAbstract, setSubmitAbstract] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Supervisor Review Modal State
  const [reviewModalProject, setReviewModalProject] = useState<ProjectSummary | null>(null);
  const [reviewAction, setReviewAction] = useState<"approve" | "reject">("approve");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewReopen, setReviewReopen] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    if (isStudent) {
      teamsApi.getAll()
        .then((res) => {
          if (res.teams && res.teams.length > 0) {
            setStudentTeam(res.teams[0]);
          }
        })
        .catch(() => {});
    }
  }, [isStudent]);

  const handleStudentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!submitTitle.trim()) {
      toast.error("Project title is required");
      return;
    }
    if (!submitAbstract.trim()) {
      toast.error("Proposal abstract / problem statement is required");
      return;
    }

    setSubmitting(true);
    try {
      await plagiarismApi.studentSubmitProposal({
        title: submitTitle.trim(),
        abstract: submitAbstract.trim(),
      });
      toast.success("Graduation proposal submitted for supervisor review! ✓");
      setShowSubmitModal(false);
      setSubmitTitle("");
      setSubmitAbstract("");
      teamsApi.getAll().then((res) => {
        if (res.teams && res.teams.length > 0) setStudentTeam(res.teams[0]);
      });
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to submit proposal");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewModalProject) return;

    setReviewing(true);
    try {
      await plagiarismApi.reviewProject(reviewModalProject.id, {
        action: reviewAction,
        notes: reviewNotes.trim() || undefined,
        reopen_submission: reviewReopen,
      });
      toast.success(
        reviewAction === "approve"
          ? `Project "${reviewModalProject.title || reviewModalProject.name}" approved!`
          : `Project rejected. Feedback sent to student team.`
      );
      setReviewModalProject(null);
      setReviewNotes("");
      setReviewReopen(false);
      load();
    } catch (e: any) {
      toast.error(e?.message || "Failed to complete review");
    } finally {
      setReviewing(false);
    }
  };

  const viewFiles = async (project: ProjectSummary | { id: string; title: string; name: string }) => {
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

  const handleRunSemanticSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!semanticQuery.trim()) {
      toast.error("Please enter a proposed topic, problem statement, or abstract");
      return;
    }

    setSearchingSemantic(true);
    try {
      const res = await plagiarismApi.semanticSearch({
        query: semanticQuery.trim(),
        threshold: semanticThreshold,
        top_k: 25,
        department: semanticDept.trim() || undefined,
        university: semanticUni.trim() || undefined,
      });

      setSemanticResults(res.projects || []);
      setModelUsed(res.model_used || "bge-m3");
      setHasSearched(true);
      if ((res.projects || []).length === 0) {
        toast("No high-similarity projects found for this proposal", { icon: "✅" });
      }
    } catch (e: any) {
      toast.error(e?.message || "Semantic proposal search failed");
    } finally {
      setSearchingSemantic(false);
    }
  };

  const filtered = projects.filter((p: ProjectSummary) => {
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

        {/* Top View Mode Navigation Tabs */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-surface/70 border border-border/80">
          <button
            onClick={() => setActiveTab("repository")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "repository"
                ? "bg-primary text-primary-text shadow-sm"
                : "text-text-muted hover:text-text-main hover:bg-surface"
            }`}
          >
            <FolderOpen className="w-3.5 h-3.5" /> Project Repository
          </button>
          <button
            onClick={() => setActiveTab("semantic")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "semantic"
                ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-sm"
                : "text-text-muted hover:text-text-main hover:bg-surface"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-300" /> AI Semantic Proposal Search
          </button>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* TAB 1: PROJECT REPOSITORY                                                  */}
      {/* ========================================================================= */}
      {activeTab === "repository" && (
        <>
          {/* Student Proposal Status Banner */}
          {isStudent && (
            <div className="mb-6 p-5 rounded-2xl glass-card border border-glass-border">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className={`p-3 rounded-xl border ${studentTeam?.submission_allowed ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500" : "bg-primary/10 border-primary/20 text-primary"}`}>
                    {studentTeam?.submission_allowed ? <Unlock className="w-6 h-6" /> : <Lock className="w-6 h-6" />}
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-text-main flex items-center gap-2">
                      Graduation Proposal Submission Status
                      {studentTeam?.submission_allowed ? (
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                          1-Time Window Active
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface text-text-muted border border-glass-border">
                          Submission Locked
                        </span>
                      )}
                    </h3>
                    <p className="text-xs text-text-muted mt-1 max-w-2xl leading-relaxed">
                      {studentTeam?.submission_allowed
                        ? `Your faculty supervisor has authorized a one-time proposal submission for team "${studentTeam.name}". Once submitted, your proposal will enter academic review.`
                        : filtered.length > 0
                        ? `Your proposal is currently recorded in the institutional database. Status: ${filtered[0].status?.toUpperCase()}${filtered[0].review_notes ? ` • Note: ${filtered[0].review_notes}` : ""}`
                        : "Submissions require approval from your faculty supervisor. Please consult your academic department chair to unlock a one-time proposal window."}
                    </p>
                  </div>
                </div>

                {studentTeam?.submission_allowed && (
                  <button
                    onClick={() => setShowSubmitModal(true)}
                    className="btn-primary flex items-center gap-2 whitespace-nowrap shadow-md"
                  >
                    <Send className="w-4 h-4" /> Submit Proposal
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="mb-4 flex justify-end">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="input-field w-full pl-9"
                placeholder={t("search_projects")}
              />
            </div>
          </div>

          {loading && projects.length === 0 ? (
            <div className="flex items-center justify-center min-h-[40vh] text-text-muted">
              <RefreshCw className="w-6 h-6 animate-spin text-accent" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="glass-panel p-10 text-center text-text-muted rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
              <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-500">
                <FolderOpen className="w-6 h-6" />
              </span>
              {t("no_projects_found")}
            </div>
          ) : (
            <div className="glass-panel overflow-hidden rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
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
                    {paged.map((p: ProjectSummary) => (
                      <tr key={p.id} className="hover:bg-surface/50 transition-colors border-b border-border/40 last:border-0">
                        <td className="py-3 px-4">
                          <div className="flex items-start gap-3">
                            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500">
                              <FolderOpen className="w-4 h-4" />
                            </span>
                            <div className="min-w-0">
                              <div className="font-medium text-text-main truncate">{p.title || p.name}</div>
                              {p.abstract && (
                                <div className="text-xs text-text-muted truncate max-w-[280px]">
                                  {p.abstract}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-text-muted">{p.university || "—"}</td>
                        <td className="py-3 px-4 text-text-muted">{p.department || "—"}</td>
                        <td className="py-3 px-4 text-text-muted">{p.year ?? "—"}</td>
                        <td className="py-3 px-4">
                          <span
                            className={
                              p.status === "pending_review"
                                ? "inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400 ring-1 ring-amber-500/30"
                                : p.status === "rejected"
                                ? "inline-flex items-center gap-1 rounded-md bg-red-500/15 px-2.5 py-0.5 text-xs font-semibold text-red-600 dark:text-red-400 ring-1 ring-red-500/30"
                                : "inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/30"
                            }
                          >
                            {p.status === "pending_review" ? "PENDING REVIEW" : (p.status?.toUpperCase() || "APPROVED")}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-end gap-2">
                            {p.status === "pending_review" && !isStudent && (
                              <button
                                onClick={() => {
                                  setReviewModalProject(p);
                                  setReviewAction("approve");
                                  setReviewNotes("");
                                  setReviewReopen(false);
                                }}
                                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-primary text-primary-text shadow-sm hover:bg-primary-hover transition-colors"
                                title="Review Proposal"
                              >
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                Review
                              </button>
                            )}
                            {p.status === "pending" && !isStudent && (
                              <button
                                onClick={() => approveProject(p)}
                                disabled={approvingId === p.id}
                                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-500 text-white shadow-sm hover:bg-emerald-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
                            {!isStudent && (
                              <button
                                onClick={() => deleteProject(p)}
                                className="btn-danger-icon"
                                title={t("delete")}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
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
        </>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: AI SEMANTIC PROPOSAL SEARCH (SPEC STEP 2.A)                        */}
      {/* ========================================================================= */}
      {activeTab === "semantic" && (
        <div className="space-y-6">
          {/* Proposal Input & Filter Card */}
          <div className="glass-panel p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-text-main flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-purple-500" />
                  AI Semantic Proposal & Abstract Search
                </h2>
                <p className="text-xs text-text-muted mt-1 max-w-2xl leading-relaxed">
                  Enter your proposed project topic, problem statement, or abstract in <strong>English or Arabic</strong>.
                  Our dense neural semantic model (BAAI/bge-m3) performs multilingual vector similarity matching across all indexed projects in the database.
                </p>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-purple-500/10 text-purple-500 border border-purple-500/20 flex-shrink-0">
                Model: {modelUsed} (1024-d)
              </span>
            </div>

            <form onSubmit={handleRunSemanticSearch} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-text-muted uppercase mb-1.5">
                  Proposed Topic / Problem Statement / Abstract
                </label>
                <textarea
                  value={semanticQuery}
                  onChange={(e) => setSemanticQuery(e.target.value)}
                  rows={4}
                  className="input-field w-full font-sans text-sm resize-y leading-relaxed"
                  placeholder="e.g. Design and implementation of an autonomous robotics navigation system utilizing LIDAR and computer vision for obstacle avoidance in warehouse environments... (or Arabic: نظام التحكم الذكي للروبوتات المتنقلة)"
                />
              </div>

              {/* Optional Filters & Threshold */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
                <div>
                  <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                    Department (Optional)
                  </label>
                  <input
                    value={semanticDept}
                    onChange={(e) => setSemanticDept(e.target.value)}
                    className="input-field w-full text-xs"
                    placeholder="e.g. Computer Science"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-text-muted uppercase mb-1">
                    University (Optional)
                  </label>
                  <input
                    value={semanticUni}
                    onChange={(e) => setSemanticUni(e.target.value)}
                    className="input-field w-full text-xs"
                    placeholder="e.g. Baghdad University"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-semibold text-text-muted uppercase">
                      Min Similarity Threshold
                    </label>
                    <span className="text-xs font-bold text-primary font-mono">
                      {Math.round(semanticThreshold * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.10"
                    max="0.80"
                    step="0.05"
                    value={semanticThreshold}
                    onChange={(e) => setSemanticThreshold(parseFloat(e.target.value))}
                    className="w-full accent-primary cursor-pointer mt-1.5"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={searchingSemantic || !semanticQuery.trim()}
                  className="px-5 py-2.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-md hover:from-purple-500 hover:to-indigo-500 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {searchingSemantic ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Analyzing Semantic Vector Embeddings...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 text-amber-300" />
                      Search Existing Projects
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Results Area */}
          {hasSearched && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text-main flex items-center gap-2">
                  <span>Semantic Match Results</span>
                  <span className="px-2 py-0.5 rounded-md text-xs bg-surface border border-border text-text-muted">
                    {semanticResults.length} matching project(s)
                  </span>
                </h3>
              </div>

              {semanticResults.length === 0 ? (
                <div className="glass-panel p-10 text-center rounded-2xl border border-slate-200 dark:border-slate-800">
                  <CheckCircle2 className="w-12 h-12 mx-auto text-emerald-500 mb-2" />
                  <h4 className="font-bold text-text-main text-base">High Originality Detected</h4>
                  <p className="text-sm text-text-muted mt-1 max-w-md mx-auto">
                    No existing projects in the database match your proposed topic above the {Math.round(semanticThreshold * 100)}% similarity threshold. This proposal appears to be novel!
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4">
                  {semanticResults.map((item) => {
                    const pct = item.similarity_percent;
                    const badgeColor =
                      pct >= 75
                        ? "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30"
                        : pct >= 50
                        ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
                        : "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30";

                    return (
                      <div
                        key={item.project_id}
                        className="glass-card rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-shadow space-y-3"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/50 pb-3">
                          <div className="min-w-0">
                            <h4 className="font-bold text-base text-text-main truncate">
                              {item.title || item.name}
                            </h4>
                            <div className="flex items-center gap-3 text-xs text-text-muted mt-1 flex-wrap">
                              {item.university && (
                                <span className="flex items-center gap-1">
                                  <Building2 className="w-3.5 h-3.5 text-text-muted" />
                                  {item.university}
                                </span>
                              )}
                              {item.department && (
                                <span className="flex items-center gap-1">
                                  <GraduationCap className="w-3.5 h-3.5 text-text-muted" />
                                  {item.department}
                                </span>
                              )}
                              {item.year && (
                                <span className="flex items-center gap-1">
                                  <Calendar className="w-3.5 h-3.5 text-text-muted" />
                                  {item.year}
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-3 flex-shrink-0">
                            <div className={`px-3 py-1 rounded-xl text-xs font-bold border ${badgeColor} flex items-center gap-1.5`}>
                              {pct >= 75 ? (
                                <AlertTriangle className="w-3.5 h-3.5" />
                              ) : (
                                <Sparkles className="w-3.5 h-3.5" />
                              )}
                              {pct}% Match
                            </div>
                            <button
                              onClick={() => viewFiles({ id: item.project_id, title: item.title, name: item.name })}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface hover:bg-surface/80 border border-border transition-colors flex items-center gap-1 text-text-main"
                            >
                              <FileText className="w-3.5 h-3.5" /> View Files
                            </button>
                          </div>
                        </div>

                        {item.abstract && (
                          <div className="text-xs text-text-muted leading-relaxed line-clamp-3 bg-surface/30 p-3 rounded-xl border border-border/30">
                            <span className="font-semibold text-text-main">Abstract: </span>
                            {item.abstract}
                          </div>
                        )}

                        <div className="flex items-center justify-between text-[11px] text-text-muted pt-1">
                          <span className="font-mono truncate max-w-md">
                            Matched file: <strong className="text-primary font-medium">{item.top_matching_file}</strong>
                          </span>
                          <span className="font-mono">
                            Cosine Sim: {item.similarity_raw.toFixed(3)} (Calibrated: {(item.similarity * 100).toFixed(1)}%)
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Student Proposal Submission Modal */}
      {showSubmitModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-xl p-6 rounded-2xl shadow-2xl border border-glass-border">
            <div className="flex items-start justify-between mb-4 border-b border-border/50 pb-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20">
                  <Send className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-text-main">Submit Graduation Project Proposal</h2>
                  <p className="text-xs text-text-muted mt-0.5">
                    Authorized by your academic supervisor for team &ldquo;{studentTeam?.name}&rdquo;
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowSubmitModal(false)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleStudentSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-text-main mb-1.5">
                  Project Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  autoComplete="off"
                  placeholder="e.g. Smart IoT Monitoring & Fault Detection Platform"
                  value={submitTitle}
                  onChange={(e) => setSubmitTitle(e.target.value)}
                  className="input-field w-full"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-main mb-1.5">
                  Proposed Abstract / Problem Statement <span className="text-red-500">*</span>
                </label>
                <textarea
                  required
                  rows={4}
                  placeholder="Detail the technical objectives, methodologies, algorithms, and expected deliverables..."
                  value={submitAbstract}
                  onChange={(e) => setSubmitAbstract(e.target.value)}
                  className="input-field w-full resize-none leading-relaxed"
                />
              </div>

              <div className="p-3.5 rounded-xl bg-surface/50 border border-glass-border text-xs text-text-muted flex items-start gap-2.5">
                <Clock className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                <span>
                  Once submitted, your one-time submission token will be consumed. Your proposal will be securely indexed and sent to your department supervisor for formal review.
                </span>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSubmitModal(false)}
                  className="btn-secondary px-4 py-2 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary px-5 py-2 text-xs font-semibold flex items-center gap-2 shadow-md disabled:opacity-50"
                >
                  {submitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Submitting...
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" /> Submit for Review
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Supervisor Review Decision Modal */}
      {reviewModalProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl shadow-2xl border border-glass-border">
            <div className="flex items-start justify-between mb-4 border-b border-border/50 pb-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-primary/10 text-primary border border-primary/20">
                  <MessageSquare className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-base font-bold text-text-main truncate">
                    Review Proposal: {reviewModalProject.title || reviewModalProject.name}
                  </h2>
                  <p className="text-xs text-text-muted mt-0.5">
                    Institution Committee Evaluation & Decision
                  </p>
                </div>
              </div>
              <button
                onClick={() => setReviewModalProject(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleReviewSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-text-main mb-2">
                  Review Decision
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setReviewAction("approve")}
                    className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                      reviewAction === "approve"
                        ? "bg-emerald-500/20 border-emerald-500 text-emerald-600 dark:text-emerald-400 ring-2 ring-emerald-500/30"
                        : "bg-surface/50 border-glass-border text-text-muted hover:text-text-main"
                    }`}
                  >
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" /> Approve Proposal
                  </button>

                  <button
                    type="button"
                    onClick={() => setReviewAction("reject")}
                    className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                      reviewAction === "reject"
                        ? "bg-rose-500/20 border-rose-500 text-rose-600 dark:text-rose-400 ring-2 ring-rose-500/30"
                        : "bg-surface/50 border-glass-border text-text-muted hover:text-text-main"
                    }`}
                  >
                    <XCircle className="w-4 h-4 text-rose-500" /> Request Revisions / Reject
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-main mb-1.5">
                  Supervisor Notes & Revision Feedback
                </label>
                <textarea
                  rows={3}
                  placeholder="Provide constructive feedback for the students or record committee meeting notes..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  className="input-field w-full resize-none leading-relaxed text-xs"
                />
              </div>

              {reviewAction === "reject" && (
                <label className="flex items-center gap-2 p-3 rounded-xl bg-surface/50 border border-glass-border text-xs text-text-main cursor-pointer hover:bg-surface transition-colors">
                  <input
                    type="checkbox"
                    checked={reviewReopen}
                    onChange={(e) => setReviewReopen(e.target.checked)}
                    className="rounded text-primary focus:ring-primary w-4 h-4"
                  />
                  <span>Allow student team to submit a revised proposal (Re-opens 1-time token)</span>
                </label>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setReviewModalProject(null)}
                  className="btn-secondary px-4 py-2 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={reviewing}
                  className={`px-5 py-2 rounded-xl text-xs font-semibold text-white shadow-md flex items-center gap-2 disabled:opacity-50 ${
                    reviewAction === "approve"
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-rose-600 hover:bg-rose-700"
                  }`}
                >
                  {reviewing ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Saving...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" /> Confirm Decision
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* View Project Files Modal */}
      {filesProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h2 className="text-lg font-semibold text-text-main truncate pr-2">
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
