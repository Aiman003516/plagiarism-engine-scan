import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  ShieldCheck,
  AlertTriangle,
  FileCode2,
  FileText,
  Download,
  Printer,
  ExternalLink,
  Search,
  ArrowRight,
  GitCompare,
  Code,
  Layers,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { PlagiarismScanResult, generateAuditReportText, triggerDownload } from "../../lib/api";
import DiffViewer from "../../components/DiffViewer";

interface ReportPreviewModalProps {
  report: PlagiarismScanResult | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenInScanner?: (report: PlagiarismScanResult) => void;
}

export default function ReportPreviewModal({
  report,
  isOpen,
  onClose,
  onOpenInScanner,
}: ReportPreviewModalProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activeDiffPair, setActiveDiffPair] = useState<any | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<"ALL" | "CRITICAL" | "HIGH" | "LOW">("ALL");
  const [search, setSearch] = useState("");

  if (!isOpen || !report) return null;

  const verdict = report.verdict || "SAFE";
  const overall = Number(report.overall_similarity ?? 0);
  const codeSim = Number(report.code_similarity ?? 0);
  const textSim = Number(report.text_similarity ?? 0);

  const getVerdictStyle = (v: string) => {
    switch (v) {
      case "SAFE":
        return "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30";
      case "LOW":
        return "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30";
      case "HIGH":
        return "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30";
      case "CRITICAL":
      default:
        return "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30";
    }
  };

  const handleExportTxt = () => {
    try {
      const text = generateAuditReportText(report);
      const cleanName = (report.project_name || report.id || "report").replace(/[^a-zA-Z0-9_-]/g, "_");
      triggerDownload(text, `${cleanName}_audit_report.txt`);
    } catch (e: any) {
      console.error("Export error", e);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleOpenScanner = () => {
    if (onOpenInScanner) {
      onOpenInScanner(report);
    } else {
      navigate(`/scan?project=${encodeURIComponent(report.project_name || report.id || "")}`);
    }
    onClose();
  };

  const comparisons = report.comparisons || [];
  const filteredComparisons = comparisons.filter((c: any) => {
    const score = Number(c.fusion_score ?? c.similarity ?? 0);
    if (filterSeverity === "CRITICAL" && score < 75) return false;
    if (filterSeverity === "HIGH" && (score < 45 || score >= 75)) return false;
    if (filterSeverity === "LOW" && score >= 45) return false;

    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const fa = (c.file_a || "").toLowerCase();
    const fb = (c.file_b || "").toLowerCase();
    const pb = (c.project_b || "").toLowerCase();
    return fa.includes(q) || fb.includes(q) || pb.includes(q);
  });

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-background/80 backdrop-blur-md z-[130]"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        className="fixed inset-4 md:inset-8 lg:inset-12 z-[131] glass-panel bg-card/95 border border-border shadow-2xl rounded-2xl flex flex-col overflow-hidden max-w-6xl mx-auto"
      >
        {/* Header */}
        <header className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0 bg-surface/40">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <FileCode2 className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg md:text-xl font-bold text-text-main truncate">
                  {report.project_name || "Scan Report"}
                </h2>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${getVerdictStyle(verdict)}`}>
                  {verdict}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-md bg-accent/20 text-accent-text font-mono">
                  {report.scan_type || "Corpus Deep Scan"}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                ID: <span className="font-mono">{report.id || "N/A"}</span> • {report.timestamp || new Date().toLocaleString()}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleExportTxt}
              className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
              title="Export as Text Audit Report"
            >
              <Download className="w-3.5 h-3.5" /> <span className="hidden sm:inline">{t("export_txt") || "Export"}</span>
            </button>
            <button
              onClick={handlePrint}
              className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
              title="Print or Save PDF"
            >
              <Printer className="w-3.5 h-3.5" /> <span className="hidden sm:inline">{t("print_pdf") || "Print"}</span>
            </button>
            <button
              onClick={handleOpenScanner}
              className="btn-primary text-xs px-3.5 py-1.5 flex items-center gap-1.5"
            >
              <ExternalLink className="w-3.5 h-3.5" /> <span className="hidden sm:inline">{t("open_in_scanner") || "Open in Scanner"}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl hover:bg-surface-hover text-text-muted hover:text-text-main transition-colors ml-1"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Executive KPI Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("overall_similarity") || "Overall Similarity"}</span>
              <span className={`text-2xl font-bold ${overall >= 65 ? "text-rose-600 dark:text-rose-400" : overall >= 35 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                {overall}%
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("code_similarity") || "Code Similarity"}</span>
              <span className="text-2xl font-bold text-text-main flex items-center justify-center gap-1">
                <Code className="w-4 h-4 text-primary" /> {codeSim}%
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("text_similarity") || "Text Similarity"}</span>
              <span className="text-2xl font-bold text-text-main flex items-center justify-center gap-1">
                <FileText className="w-4 h-4 text-accent-text" /> {textSim}%
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("files_analyzed") || "Files Analyzed"}</span>
              <span className="text-2xl font-bold text-text-main">
                {report.total_files || (report.code_files_count || 0) + (report.text_files_count || 0) || 0}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("total_loc") || "Total LOC"}</span>
              <span className="text-2xl font-bold text-text-main">
                {(report.total_loc || 0).toLocaleString()}
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-surface/80 border border-border/70 text-center">
              <span className="text-xs text-text-muted block mb-1">{t("detected_stack") || "Detected Stack"}</span>
              <div className="flex flex-wrap gap-1 justify-center max-h-12 overflow-y-auto">
                {(report.languages_detected && report.languages_detected.length > 0) ? (
                  report.languages_detected.map((lang: string) => (
                    <span key={lang} className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono">
                      {lang}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-text-muted">Standard</span>
                )}
              </div>
            </div>
          </div>

          {/* Suspicious Pairs Section */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-text-main flex items-center gap-2">
                  <Layers className="w-4 h-4 text-primary" /> {t("matched_suspicious_pairs") || "Matched Suspicious Pairs"}
                </h3>
                <p className="text-xs text-text-muted">
                  Showing {filteredComparisons.length} of {comparisons.length} compared file pairs
                </p>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {/* Search */}
                <div className="relative w-full sm:w-56">
                  <Search className="w-3.5 h-3.5 text-text-muted absolute start-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("search") || "Search files..."}
                    className="input-field text-xs py-1.5 ps-8 w-full"
                  />
                </div>

                {/* Severity Pills */}
                <div className="flex items-center gap-1 bg-surface-hover/60 p-0.5 rounded-lg border border-border/60 text-xs">
                  {(["ALL", "CRITICAL", "HIGH", "LOW"] as const).map((sev) => (
                    <button
                      key={sev === "ALL" ? (t("filter_all") || "ALL") : sev === "CRITICAL" ? (t("critical") || "CRITICAL") : sev === "HIGH" ? (t("high") || "HIGH") : (t("low") || "LOW")}
                      onClick={() => setFilterSeverity(sev)}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                        filterSeverity === sev
                          ? "bg-accent text-accent-text font-bold shadow-sm"
                          : "text-text-muted hover:text-text-main"
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Table */}
            {filteredComparisons.length === 0 ? (
              <div className="p-8 text-center text-text-muted rounded-xl bg-surface/30 border border-border/50 text-xs">
                No matched file pairs match the current filter.
              </div>
            ) : (
              <div className="border border-border/80 rounded-xl overflow-hidden bg-surface/40">
                <table className="w-full text-xs text-start">
                  <thead className="bg-surface-hover/60 border-b border-border/80 text-text-muted font-semibold">
                    <tr>
                      <th className="px-4 py-2.5 text-start">{t("source_file") || "File in Target Project"}</th>
                      <th className="px-4 py-2.5 text-start">{t("matched_target") || "Matched Repository File"}</th>
                      <th className="px-4 py-2.5 text-center">{t("exact_ast_match") || "Exact"}</th>
                      <th className="px-4 py-2.5 text-center">{t("text_similarity") || "Semantic"}</th>
                      <th className="px-4 py-2.5 text-center">{t("fusion_score") || "Fusion Score"}</th>
                      <th className="px-4 py-2.5 text-end">{t("actions") || "Action"}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {filteredComparisons.slice(0, 50).map((c: any, idx: number) => {
                      const fScore = Math.round(Number(c.fusion_score ?? c.similarity ?? 0));
                      const wScore = Math.round(Number(c.winnowing_score ?? c.exact_match ?? 0));
                      const sScore = Math.round(Number(c.semantic_score ?? c.semantic_sim ?? 0));

                      return (
                        <tr key={idx} className="hover:bg-surface-hover/40 transition-colors">
                          <td className="px-4 py-2.5 font-mono text-text-main max-w-xs truncate" title={c.file_a}>
                            {c.file_a}
                          </td>
                          <td className="px-4 py-2.5 font-mono text-text-muted max-w-xs truncate" title={`${c.project_b || ""} / ${c.file_b || ""}`}>
                            <span className="font-semibold text-text-main">{c.project_b}</span> / {c.file_b}
                          </td>
                          <td className="px-4 py-2.5 text-center font-mono">
                            {wScore}%
                          </td>
                          <td className="px-4 py-2.5 text-center font-mono">
                            {sScore}%
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                                fScore >= 75
                                  ? "bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30"
                                  : fScore >= 45
                                  ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30"
                                  : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                              }`}
                            >
                              {fScore}%
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-end">
                            <button
                              onClick={() => setActiveDiffPair(c)}
                              className="btn-secondary text-[11px] px-2.5 py-1 inline-flex items-center gap-1"
                            >
                              <GitCompare className="w-3 h-3" /> {t("view_diff") || "Diff"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Inline Diff Modal if clicked */}
        {activeDiffPair && (
          <div className="fixed inset-0 z-[140] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="glass-panel w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl overflow-hidden bg-card border border-border shadow-2xl">
              <div className="px-5 py-3 border-b border-border flex items-center justify-between bg-surface/50">
                <div className="flex items-center gap-2 truncate">
                  <GitCompare className="w-4 h-4 text-primary shrink-0" />
                  <span className="font-semibold text-xs md:text-sm truncate">
                    {activeDiffPair.file_a} vs {activeDiffPair.project_b}/{activeDiffPair.file_b}
                  </span>
                </div>
                <button
                  onClick={() => setActiveDiffPair(null)}
                  className="p-1 rounded-lg hover:bg-surface-hover text-text-muted hover:text-text-main"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-auto p-4">
                <DiffViewer
                  projectA={report.project_name || report.id}
                  fileA={activeDiffPair.file_a}
                  projectB={activeDiffPair.project_b}
                  fileB={activeDiffPair.file_b}
                />
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
