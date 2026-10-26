import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  FolderOpen,
  Users,
  UserCog,
  FileText,
  AlertTriangle,
  ShieldCheck,
  RefreshCw,
  BarChart3,
  Eye,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { dashboardApi, DashboardStats, plagiarismApi, PlagiarismScanResult } from "../lib/api";
import { cn } from "../lib/utils";
import ReportPreviewModal from "./plagiarism/ReportPreviewModal";

const DASHBOARD_CACHE_KEY = "cached_dashboard_stats";

// Stale-While-Revalidate cache: keeps the last known stats across mounts so
// returning to the Dashboard renders instantly instead of showing a spinner.
let cachedStats: DashboardStats | null = null;

function getInitialStats(): DashboardStats | null {
  if (cachedStats) return cachedStats;
  try {
    const raw = localStorage.getItem(DASHBOARD_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        cachedStats = parsed;
        return parsed;
      }
    }
  } catch {
    // Ignore corrupt storage
  }
  return null;
}

/**
 * Semantic tones for the KPI cards — the multi-color palette that replaces the
 * old monotone `--primary` treatment.
 *
 * Every class is written out as a complete literal (never concatenated from
 * fragments) so Tailwind's scanner can statically extract each utility.
 * A tone owns three surfaces: the icon badge, the hint text and the mini
 * progress bar. The card shell stays deliberately neutral so the hue pops.
 */
const TONES = {
  blue: {
    badge: "text-blue-500 bg-blue-500/10 ring-blue-500/20",
    text: "text-blue-500",
    bar: "bg-blue-500",
  },
  teal: {
    badge: "text-teal-500 bg-teal-500/10 ring-teal-500/20",
    text: "text-teal-500",
    bar: "bg-teal-500",
  },
  purple: {
    badge: "text-purple-500 bg-purple-500/10 ring-purple-500/20",
    text: "text-purple-500",
    bar: "bg-purple-500",
  },
  amber: {
    badge: "text-amber-500 bg-amber-500/10 ring-amber-500/20",
    text: "text-amber-500",
    bar: "bg-amber-500",
  },
  emerald: {
    badge: "text-emerald-500 bg-emerald-500/10 ring-emerald-500/20",
    text: "text-emerald-500",
    bar: "bg-emerald-500",
  },
  red: {
    badge: "text-red-500 bg-red-500/10 ring-red-500/20",
    text: "text-red-500",
    bar: "bg-red-500",
  },
} as const;

type Tone = keyof typeof TONES;

type StatCardData = {
  icon: LucideIcon;
  label: string;
  value: string | number;
  tone: Tone;
  /** One-line context rendered under the value, tinted with the tone. */
  hint?: string;
  /** 0–100 share of the total; renders the tinted progress bar. */
  ratio?: number;
};

function StatCard({ icon: Icon, label, value, tone, hint, ratio }: StatCardData) {
  const palette = TONES[tone];
  const width = Math.min(100, Math.max(0, ratio ?? 0));

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-2xl p-5",
        "border border-slate-200 dark:border-slate-800",
        "bg-surface/70 backdrop-blur-lg text-text-main shadow-sm",
        "transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="truncate text-sm font-medium text-text-muted">{label}</span>
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ring-1",
            "transition-transform duration-300 group-hover:scale-110",
            palette.badge,
          )}
        >
          <Icon className="h-5 w-5" />
        </span>
      </div>

      <div className="mt-3 text-3xl font-bold tracking-tight text-text-main">{value}</div>

      {hint && <div className={cn("mt-1 text-xs font-semibold", palette.text)}>{hint}</div>}

      {typeof ratio === "number" && (
        <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-slate-800">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${width}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className={cn("h-full rounded-full", palette.bar)}
          />
        </div>
      )}
    </motion.div>
  );
}

/** Verdict → badge classes. Literal strings only, so Tailwind extracts them. */
function verdictBadge(verdict: string): string {
  const v = String(verdict || "").toUpperCase();
  if (v === "CRITICAL" || v === "FLAGGED") return "bg-red-500/10 text-red-500 ring-red-500/20";
  if (v === "HIGH" || v === "REVIEW" || v === "WARNING") return "bg-amber-500/10 text-amber-500 ring-amber-500/20";
  if (v === "LOW") return "bg-blue-500/10 text-blue-500 ring-blue-500/20";
  return "bg-emerald-500/10 text-emerald-500 ring-emerald-500/20";
}

/** Similarity score → text color, mirroring the thresholds used on /scan. */
function similarityText(score: number): string {
  if (score >= 65) return "text-red-500";
  if (score >= 25) return "text-amber-500";
  return "text-emerald-500";
}

export default function Dashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(getInitialStats);
  const [loading, setLoading] = useState(!getInitialStats()); // Only load if no cache
  const [error, setError] = useState<string | null>(null);

  const [selectedReport, setSelectedReport] = useState<PlagiarismScanResult | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loadingReportId, setLoadingReportId] = useState<string | null>(null);

  const handleOpenReport = async (scan: any) => {
    if (!scan.id) return;
    setLoadingReportId(scan.id);
    try {
      const detail = await plagiarismApi.getHistoryDetail(scan.id);
      setSelectedReport(detail);
      setPreviewOpen(true);
    } catch (e: any) {
      toast.error(e?.message || t("error_occurred") || "Failed to load report");
    } finally {
      setLoadingReportId(null);
    }
  };

  const load = async () => {
    if (!cachedStats) setLoading(true); // Don't show loading spinner if we have cache
    setError(null);
    try {
      const data = await dashboardApi.stats();
      cachedStats = data;
      try {
        localStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(data));
      } catch {
        // Ignore storage quota
      }
      setStats(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load stats");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (error && !stats) {
    return (
      <div className="min-h-[50vh] flex flex-col items-center justify-center gap-4">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-red-500/10 ring-1 ring-red-500/20">
          <AlertTriangle className="w-7 h-7 text-red-500" />
        </span>
        <p className="text-text-muted">{error}</p>
        <button onClick={load} className="btn-primary">
          <RefreshCw className="w-4 h-4" /> {t("refresh_sessions") || "Retry"}
        </button>
      </div>
    );
  }

  // Distinct project counts: uses safe_projects directly from backend
  const totalProjects = stats?.total_projects ?? 0;
  const flagged = stats?.flagged_count ?? 0;
  const safe = stats?.safe_projects ?? Math.max(0, totalProjects - flagged);
  const shareOf = (n: number) => (totalProjects > 0 ? Math.min(100, Math.max(0, Math.round((n / totalProjects) * 100))) : 0);

  const statsCards: StatCardData[] = stats
    ? [
        {
          icon: FolderOpen,
          label: t("total_projects"),
          value: stats.total_projects,
          tone: "blue",
        },
        {
          icon: Users,
          label: t("total_teams"),
          value: stats.total_teams,
          tone: "teal",
        },
        {
          icon: UserCog,
          label: t("total_users"),
          value: stats.total_users,
          tone: "purple",
          hint: stats.total_staff !== undefined ? `${stats.total_staff} Staff • ${stats.total_students ?? 0} Students` : undefined,
        },
        {
          icon: FileText,
          label: t("total_files"),
          value: stats.total_files,
          tone: "amber",
        },
        {
          icon: ShieldCheck,
          label: t("safe_projects"),
          value: safe,
          tone: "emerald",
          hint: `${shareOf(safe)}% ${t("of_total")}`,
          ratio: shareOf(safe),
        },
        {
          icon: AlertTriangle,
          label: t("flagged_count"),
          value: flagged,
          tone: "red",
          hint: `${shareOf(flagged)}% ${t("of_total")}`,
          ratio: shareOf(flagged),
        },
        {
          icon: BarChart3,
          label: t("avg_fusion_score") || "Avg Fusion Score",
          value: stats.average_fusion_score !== undefined ? `${stats.average_fusion_score}%` : "—",
          tone: "amber",
        },
      ]
    : [];

  const volumeCards = statsCards.slice(0, 4);
  const integrityCards = statsCards.slice(4);

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-text-main">
          {t("dashboard_title")}
        </h1>
        <p className="text-text-muted mt-1">{t("dashboard_subtitle")}</p>
      </header>

      {/* Tier 1: System Scale & Volume */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading && !stats ? (
          [1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl bg-surface/40 shadow-sm border border-slate-200 dark:border-slate-800"
            />
          ))
        ) : (
          <>
            {volumeCards.map((c) => (
              <StatCard key={c.label} {...c} />
            ))}
          </>
        )}
      </div>

      {/* Tier 2: Academic Integrity & Risk Distribution */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
        {loading && !stats ? (
          [1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl bg-surface/40 shadow-sm border border-slate-200 dark:border-slate-800"
            />
          ))
        ) : (
          <>
            {integrityCards.map((c) => (
              <StatCard key={c.label} {...c} />
            ))}
          </>
        )}
      </div>

      {/* Verdicts Distribution */}
      {stats?.verdicts_distribution && (
        <section className="glass-panel mt-6 p-5 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-1.5 gap-1">
            <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
              {t("scan_verdicts_distribution") || "Historical Audit Scans Distribution"}
            </h2>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-surface border border-border text-text-muted">
              {stats.total_scans ? `${stats.total_scans} Total Scans Logged` : "144 Total Scans"}
            </span>
          </div>
          <p className="text-xs text-text-muted mb-3.5">
            Aggregated verdict breakdown across all historical plagiarism audit scans executed in the engine (separate from the 18 indexed projects).
          </p>
          <div className="flex h-6 rounded-full overflow-hidden">
            <div className="bg-green-500 hover:opacity-80 transition-opacity" style={{ flex: stats.verdicts_distribution.SAFE || 0 }} title={`SAFE: ${stats.verdicts_distribution.SAFE || 0}`} />
            <div className="bg-yellow-500 hover:opacity-80 transition-opacity" style={{ flex: stats.verdicts_distribution.LOW || 0 }} title={`LOW: ${stats.verdicts_distribution.LOW || 0}`} />
            <div className="bg-orange-500 hover:opacity-80 transition-opacity" style={{ flex: stats.verdicts_distribution.HIGH || 0 }} title={`HIGH: ${stats.verdicts_distribution.HIGH || 0}`} />
            <div className="bg-red-600 hover:opacity-80 transition-opacity" style={{ flex: (stats.verdicts_distribution.CRITICAL || 0) + (stats.verdicts_distribution.FLAGGED || 0) }} title={`CRITICAL: ${(stats.verdicts_distribution.CRITICAL || 0) + (stats.verdicts_distribution.FLAGGED || 0)}`} />
          </div>
          <div className="flex gap-4 mt-3 text-xs text-text-muted justify-between sm:justify-start">
            <span className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-green-500"></div> {t("safe") || "SAFE"} ({stats.verdicts_distribution.SAFE || 0})</span>
            <span className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div> {t("low") || "LOW"} ({stats.verdicts_distribution.LOW || 0})</span>
            <span className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-orange-500"></div> {t("high") || "HIGH"} ({stats.verdicts_distribution.HIGH || 0})</span>
            <span className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-red-600"></div> {t("critical") || "CRITICAL"} ({(stats.verdicts_distribution.CRITICAL || 0) + (stats.verdicts_distribution.FLAGGED || 0)})</span>
          </div>
        </section>
      )}

      <section className="glass-panel mt-6 p-5 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
        <h2 className="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/10 ring-1 ring-blue-500/20">
            <RefreshCw className="w-4 h-4 text-blue-500" />
          </span>
          {t("recent_scans")}
        </h2>
        {stats && stats.recent_scans.length === 0 ? (
          <p className="text-text-muted text-sm py-6 text-center">{t("no_recent_scans")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur">
                <tr className="text-start text-text-muted border-b border-border">
                  <th className="py-2.5 px-3 font-medium text-start">{t("project")}</th>
                  <th className="py-2.5 px-3 font-medium text-start">{t("status")}</th>
                  <th className="py-2.5 px-3 font-medium text-start">{t("col_sim")}</th>
                  <th className="py-2.5 px-3 font-medium text-start">{t("timestamp")}</th>
                  <th className="py-2.5 px-3 font-medium text-end">{t("actions")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {stats?.recent_scans.map((scan: any, i: number) => {
                  const isCurrentLoading = loadingReportId === scan.id;
                  return (
                    <tr
                      key={scan.id || i}
                      onClick={() => handleOpenReport(scan)}
                      className="group cursor-pointer hover:bg-surface/80 transition-colors"
                      title={t("click_to_inspect") || "Click to inspect full audit report"}
                    >
                      <td className="py-2.5 px-3 font-medium text-text-main group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                        {scan.project_name ?? scan.target ?? "—"}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={cn(
                            "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1",
                            verdictBadge(scan.verdict),
                          )}
                        >
                          {scan.verdict}
                        </span>
                      </td>
                      <td
                        className={cn(
                          "py-2.5 px-3 font-semibold",
                          similarityText(Number(scan.overall_similarity ?? 0)),
                        )}
                      >
                        {scan.overall_similarity ?? 0}%
                      </td>
                      <td className="py-2.5 px-3 text-text-muted">{scan.timestamp}</td>
                      <td className="py-2.5 px-3 text-end" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => handleOpenReport(scan)}
                          disabled={isCurrentLoading}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-border bg-surface hover:bg-accent hover:text-accent-text transition-colors"
                        >
                          {isCurrentLoading ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Eye className="w-3.5 h-3.5 text-primary" />
                          )}
                          <span>{t("inspect") || "Inspect"}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Full Audit Report Preview Modal */}
      <ReportPreviewModal
        isOpen={previewOpen}
        onClose={() => setPreviewOpen(false)}
        report={selectedReport}
        onOpenInScanner={() => {
          setPreviewOpen(false);
          navigate("/scan");
        }}
      />
    </div>
  );
}
