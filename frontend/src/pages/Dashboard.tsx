import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  FolderOpen,
  Users,
  UserCog,
  FileText,
  AlertTriangle,
  ShieldCheck,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { dashboardApi, DashboardStats } from "../lib/api";
import { cn } from "../lib/utils";

// Stale-While-Revalidate cache: keeps the last known stats across mounts so
// returning to the Dashboard renders instantly instead of showing a spinner.
let cachedStats: DashboardStats | null = null;

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
  if (v === "FLAGGED") return "bg-red-500/10 text-red-500 ring-red-500/20";
  if (v === "REVIEW" || v === "WARNING") return "bg-amber-500/10 text-amber-500 ring-amber-500/20";
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
  const [stats, setStats] = useState<DashboardStats | null>(cachedStats);
  const [loading, setLoading] = useState(!cachedStats); // Only load if no cache
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!cachedStats) setLoading(true); // Don't show loading spinner if we have cache
    setError(null);
    try {
      const data = await dashboardApi.stats();
      cachedStats = data;
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

  // "Safe" is derived on the client: the stats endpoint reports the project
  // total and the flagged count only, so clean = total − flagged.
  const totalProjects = stats?.total_projects ?? 0;
  const flagged = stats?.flagged_count ?? 0;
  const safe = Math.max(0, totalProjects - flagged);
  const shareOf = (n: number) => (totalProjects > 0 ? Math.round((n / totalProjects) * 100) : 0);

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
      ]
    : [];

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-text-main">
          {t("dashboard_title")}
        </h1>
        <p className="text-text-muted mt-1">{t("dashboard_subtitle")}</p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {loading && !stats ? (
          [1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl bg-surface/40 shadow-sm border border-slate-200 dark:border-slate-800"
            />
          ))
        ) : (
          <>
            {statsCards.map((c) => (
              <StatCard key={c.label} {...c} />
            ))}
          </>
        )}
      </div>

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
                <tr className="text-left text-text-muted border-b border-border">
                  <th className="py-2 px-3 font-medium">{t("project")}</th>
                  <th className="py-2 px-3 font-medium">{t("status")}</th>
                  <th className="py-2 px-3 font-medium">{t("col_sim")}</th>
                  <th className="py-2 px-3 font-medium">{t("timestamp")}</th>
                </tr>
              </thead>
              <tbody>
                {stats?.recent_scans.map((scan: any, i: number) => (
                  <tr key={scan.id || i} className="hover:bg-surface/50 transition-colors">
                    <td className="py-2.5 px-3">{scan.project_name ?? scan.target ?? "—"}</td>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
