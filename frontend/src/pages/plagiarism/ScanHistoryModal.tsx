import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  History,
  Clock,
  Eye,
  Trash2,
  RefreshCw,
  Search,
  X,
  Download,
  FileText,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  plagiarismApi,
  PlagiarismHistoryItem,
  PlagiarismScanResult,
  generateAuditReportText,
  triggerDownload,
} from "../../lib/api";
import { useHistoryCache } from "../../lib/useHistoryCache";
import { TableSkeleton } from "../../components/Skeletons";
import ReportPreviewModal from "./ReportPreviewModal";

interface ScanHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectReport?: (report: PlagiarismScanResult) => void;
}

export function ScanHistoryModal({ isOpen, onClose, onSelectReport }: ScanHistoryModalProps) {
  const { t } = useTranslation();
  const { historyList, loading, refresh } = useHistoryCache();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 10;
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [inspectingId, setInspectingId] = useState<string | null>(null);
  const [previewReport, setPreviewReport] = useState<PlagiarismScanResult | null>(null);

  const handleDelete = async (id: string) => {
    if (!window.confirm("Are you sure you want to delete this scan record from database?")) return;
    try {
      await plagiarismApi.deleteHistory(id);
      refresh(true);
      toast.success("Scan record deleted");
    } catch (e: any) {
      toast.error(e?.message || "Failed to delete record");
    }
  };

  const handleDownload = async (h: PlagiarismHistoryItem) => {
    setDownloadingId(h.id);
    try {
      const detail = await plagiarismApi.getHistoryDetail(h.id);
      const text = generateAuditReportText(detail);
      const cleanName = (h.project_name || h.id).replace(/[^a-zA-Z0-9_-]/g, "_");
      triggerDownload(text, `${cleanName}_audit_report.txt`);
      toast.success("Audit report downloaded");
    } catch (e: any) {
      toast.error(e?.message || "Failed to export report");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleInspect = async (h: PlagiarismHistoryItem) => {
    setInspectingId(h.id);
    try {
      const detail = await plagiarismApi.getHistoryDetail(h.id);
      setPreviewReport(detail as PlagiarismScanResult);
      if (onSelectReport) {
        onSelectReport(detail as PlagiarismScanResult);
      }
    } catch (e: any) {
      toast.error(e?.message || "Failed to inspect report");
    } finally {
      setInspectingId(null);
    }
  };

  const filtered = historyList.filter((h) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (h.project_name || "").toLowerCase().includes(q) ||
      (h.id || "").toLowerCase().includes(q)
    );
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paginatedItems = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);


  if (!isOpen) return null;

  return createPortal(
    <>
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-background/80 backdrop-blur-md z-[120]"
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 16 }}
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-4xl glass-panel shadow-2xl z-[121] overflow-hidden flex flex-col max-h-[85vh] border border-border rounded-2xl"
        >
          {/* Header */}
          <div className="p-5 border-b border-border flex justify-between items-center bg-surface/50">
            <div>
              <h3 className="text-base md:text-lg font-bold text-text-main flex items-center gap-2">
                <History className="w-5 h-5 text-primary dark:text-accent" />
                Historical Plagiarism Audit Logs & Reports
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                Review, inspect, or download permanent audit records saved in the database
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => refresh(true)}
                className="p-2 rounded-xl text-text-muted hover:text-text-main hover:bg-surface-hover transition-colors"
                title="Refresh history"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </button>
              <button
                onClick={onClose}
                className="text-text-muted hover:text-text-main p-2 hover:bg-surface-hover rounded-xl transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="p-3.5 border-b border-border bg-surface/20">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search past audit records by project name or ID..."
                className="input-field text-xs py-2 pl-9 w-full"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-main"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Content list */}
          <div className="p-5 overflow-y-auto flex-1">
            {loading && historyList.length === 0 ? (
              <TableSkeleton columns={5} rows={5} />
            ) : filtered.length === 0 ? (
              <div className="py-16 text-center text-text-muted space-y-2">
                <History className="w-8 h-8 mx-auto text-text-muted/40" />
                <p className="text-sm font-medium">No scan history records found</p>
                <p className="text-xs text-text-muted/70">
                  {search ? "Try adjusting your search query." : "Run a plagiarism scan to generate your first audit record."}
                </p>
              </div>
            ) : (
              <div className="border border-border rounded-xl overflow-hidden bg-surface/30">
                <table className="w-full text-xs text-left">
                  <thead className="bg-surface-hover/70 border-b border-border text-text-muted font-semibold">
                    <tr>
                      <th className="px-4 py-3">Project / Scan ID</th>
                      <th className="px-4 py-3 text-center">Type</th>
                      <th className="px-4 py-3 text-center">Similarity</th>
                      <th className="px-4 py-3 text-center">Verdict</th>
                      <th className="px-4 py-3 text-center">Date & Time</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {paginatedItems.map((item) => {
                      const overall = Number(item.overall_similarity ?? 0);
                      const isInspecting = inspectingId === item.id;
                      const isDownloading = downloadingId === item.id;


                      return (
                        <tr key={item.id} className="hover:bg-surface-hover/40 transition-colors">
                          <td className="px-4 py-3">
                            <span className="font-semibold text-text-main block truncate max-w-xs" title={item.project_name}>
                              {item.project_name || "Untitled Project"}
                            </span>
                            <span className="font-mono text-[10px] text-text-muted block truncate max-w-xs">
                              {item.id}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className="px-2 py-0.5 rounded bg-accent/15 text-accent-text font-mono text-[10px]">
                              {item.scan_type || "Corpus Deep Scan"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center font-bold text-sm">
                            <span
                              className={
                                overall >= 65
                                  ? "text-rose-600 dark:text-rose-400"
                                  : overall >= 35
                                  ? "text-amber-600 dark:text-amber-400"
                                  : "text-emerald-600 dark:text-emerald-400"
                              }
                            >
                              {overall}%
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                item.verdict === "SAFE"
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                                  : item.verdict === "LOW"
                                  ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
                                  : item.verdict === "HIGH"
                                  ? "bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30"
                                  : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30"
                              }`}
                            >
                              {item.verdict || "SAFE"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center text-text-muted whitespace-nowrap text-[11px]">
                            {item.timestamp ? new Date(item.timestamp).toLocaleString() : "N/A"}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => handleInspect(item)}
                                disabled={isInspecting}
                                className="btn-primary text-[11px] px-2.5 py-1 flex items-center gap-1"
                                title="Inspect interactive report"
                              >
                                {isInspecting ? (
                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                ) : (
                                  <Eye className="w-3 h-3" />
                                )}
                                <span>Inspect</span>
                              </button>
                              <button
                                onClick={() => handleDownload(item)}
                                disabled={isDownloading}
                                className="btn-secondary text-[11px] p-1.5 text-text-muted hover:text-text-main"
                                title="Download Audit Text Report"
                              >
                                {isDownloading ? (
                                  <RefreshCw className="w-3 h-3 animate-spin" />
                                ) : (
                                  <Download className="w-3 h-3" />
                                )}
                              </button>
                              <button
                                onClick={() => handleDelete(item.id)}
                                className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-500/10 transition-colors"
                                title="Delete record"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* Pagination Controls */}
                {totalPages > 1 && (
                  <div className="p-3 border-t border-border bg-surface/50 flex items-center justify-between text-xs text-text-muted">
                    <div>
                      Showing {(currentPage - 1) * PAGE_SIZE + 1} to{" "}
                      {Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length} reports
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="px-2.5 py-1 rounded-lg border border-border bg-surface hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Previous
                      </button>
                      <span className="font-semibold text-text-main">
                        {currentPage} / {totalPages}
                      </span>
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="px-2.5 py-1 rounded-lg border border-border bg-surface hover:bg-surface-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Report Preview Modal */}
      {previewReport && (
        <ReportPreviewModal
          report={previewReport}
          isOpen={!!previewReport}
          onClose={() => setPreviewReport(null)}
        />
      )}
    </>,
    document.body
  );
}
