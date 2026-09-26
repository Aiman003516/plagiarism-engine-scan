import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  FolderOpen,
  Users,
  UserCog,
  FileText,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { dashboardApi, DashboardStats } from "../lib/api";

// Stale-While-Revalidate cache: keeps the last known stats across mounts so
// returning to the Dashboard renders instantly instead of showing a spinner.
let cachedStats: DashboardStats | null = null;

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: any;
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={
        accent
          ? "glass-card border-accent/40 bg-accent-light"
          : "glass-card"
      }
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-text-muted">{label}</span>
        <Icon className="w-5 h-5 text-accent-text bg-accent rounded-lg p-1" />
      </div>
      <div className="text-3xl font-bold text-text-main mt-3">{value}</div>
    </motion.div>
  );
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
        <AlertTriangle className="w-8 h-8 text-danger" />
        <p className="text-text-muted">{error}</p>
        <button onClick={load} className="btn-primary">
          <RefreshCw className="w-4 h-4" /> {t("refresh_sessions") || "Retry"}
        </button>
      </div>
    );
  }

  const statsCards = stats
    ? [
        { icon: FolderOpen, label: t("total_projects"), value: stats.total_projects },
        { icon: Users, label: t("total_teams"), value: stats.total_teams },
        { icon: UserCog, label: t("total_users"), value: stats.total_users },
        { icon: FileText, label: t("total_files"), value: stats.total_files },
        { icon: AlertTriangle, label: t("flagged_count"), value: stats.flagged_count, accent: true },
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {loading && !stats ? (
          [1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="animate-pulse glass-card h-32 rounded-xl bg-surface/40 border border-border"
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

      <section className="glass-panel mt-6 p-5">
        <h2 className="text-lg font-semibold text-text-main mb-4 flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-accent-text bg-accent rounded p-0.5" />
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
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          scan.verdict === "FLAGGED"
                            ? "bg-red-500/10 text-red-400"
                            : "bg-emerald-500/10 text-emerald-400"
                        }`}
                      >
                        {scan.verdict}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-medium">{scan.overall_similarity ?? 0}%</td>
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
