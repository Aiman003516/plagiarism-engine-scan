import React, { useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, X, UploadCloud, ShieldAlert, Code2,
  History, Clock, Eye, Trash2, RefreshCw
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { plagiarismApi, PlagiarismHistoryItem } from "../../lib/api";
import { useScanStore } from "../../lib/scanStore";
import { useScanStreamReconnection } from "./hooks/useScanStream";

import { UploadSection } from "./UploadSection";
import { GitScanSection } from "./GitScanSection";
import { ScanProgress } from "./ScanProgress";

export function Plagiarism() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Re-attach scan stream if one is in flight
  useScanStreamReconnection();

  const [activeTab, setActiveTab] = useState<"direct" | "git">("direct");

  // Modals & History Inspection
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [historyList, setHistoryList] = useState<PlagiarismHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historySearch, setHistorySearch] = useState<string>("");

  const uploadedFiles = useScanStore((s) => s.uploadedFiles);

  const loadHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const res = await plagiarismApi.getHistory();
      if (res && res.reports) {
        setHistoryList(res.reports);
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleOpenHistory = () => {
    setIsHistoryOpen(true);
    loadHistory();
  };

  const handleDeleteHistoryReport = async (reportId: string) => {
    if (!window.confirm(t("delete_confirm"))) return;
    try {
      await plagiarismApi.deleteHistory(reportId);
      setHistoryList(prev => prev.filter(r => r.id !== reportId));
      toast.success(t("delete_record"));
    } catch (e) {
      toast.error("Failed to delete record.");
    }
  };

  const clearUpload = () => {
    useScanStore.getState().setUploadedFiles([]);
    useScanStore.getState().setProjectName("");
    useScanStore.getState().setBloatStats(0, 0);
    toast.success(t("clear_all"));
  };

  const filteredHistory = historyList.filter(h => {
    if (!historySearch.trim()) return true;
    const q = historySearch.toLowerCase();
    return (h.project_name || "").toLowerCase().includes(q) || (h.id || "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-3">
            <ShieldAlert className="w-7 h-7 text-primary dark:text-accent" />
            {t("plagiarism_title")}
          </h1>
          <p className="text-text-muted text-sm max-w-3xl leading-relaxed">
            {t("plagiarism_desc")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {uploadedFiles.length > 0 && activeTab === "direct" && (
            <button 
              onClick={clearUpload} 
              className="btn-danger px-3.5 py-2 rounded-xl text-xs gap-1.5"
            >
              <Trash2 className="w-4 h-4" />
              {t("clear_all")}
            </button>
          )}
          <button 
            onClick={handleOpenHistory}
            className="bg-surface/60 hover:bg-surface border border-glass-border rounded-xl px-4 py-2 flex items-center gap-2 text-sm font-semibold text-text-main transition-colors shrink-0 shadow-sm"
          >
            <History className="w-4 h-4 text-primary dark:text-accent" />
            {t("scan_history")}
          </button>
        </div>
      </div>

      {/* DUAL-MODE INTAKE SWITCHER TABS */}
      <div className="flex border-b border-glass-border gap-2">
        <button
          onClick={() => setActiveTab("direct")}
          className={`pb-3 px-4 font-semibold text-sm flex items-center gap-2 border-b-2 transition-all ${
            activeTab === "direct"
              ? "border-accent text-primary dark:text-accent"
              : "border-transparent text-text-muted hover:text-text-main"
          }`}
        >
          <UploadCloud className="w-4 h-4" />
          {t("tab_direct_upload")}
        </button>
        <button
          onClick={() => setActiveTab("git")}
          className={`pb-3 px-4 font-semibold text-sm flex items-center gap-2 border-b-2 transition-all ${
            activeTab === "git"
              ? "border-accent text-primary dark:text-accent"
              : "border-transparent text-text-muted hover:text-text-main"
          }`}
        >
          <Code2 className="w-4 h-4" />
          {t("tab_git_repo")}
        </button>
      </div>

      {activeTab === "direct" && <UploadSection />}
      {activeTab === "git" && <GitScanSection />}

      <ScanProgress />

      {/* Database Scan History Modal */}
      <AnimatePresence>
        {isHistoryOpen && createPortal(
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsHistoryOpen(false)}
              className="fixed inset-0 bg-background/80 backdrop-blur-md z-[120]"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl glass-panel shadow-2xl z-[121] overflow-hidden flex flex-col max-h-[85vh] border border-glass-border/50"
            >
              <div className="p-6 border-b border-glass-border flex justify-between items-center bg-surface/40">
                <div>
                  <h3 className="text-lg font-bold text-text-main flex items-center gap-2">
                    <History className="w-5 h-5 text-primary dark:text-accent" />
                    {t("history_modal_title")}
                  </h3>
                  <p className="text-xs text-text-muted mt-0.5">
                    Centralized audit reports stored in PostgreSQL database
                  </p>
                </div>
                <button 
                  onClick={() => setIsHistoryOpen(false)}
                  className="text-text-muted hover:text-text-main p-2 hover:bg-surface rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* History Search Bar */}
              <div className="p-4 border-b border-glass-border/40 bg-surface/10">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 rtl:right-3 top-1/2 -translate-y-1/2 text-text-muted" />
                  <input
                    type="text"
                    value={historySearch}
                    onChange={(e) => setHistorySearch(e.target.value)}
                    placeholder="Search past scans by project name or ID..."
                    className="w-full bg-background/50 border border-glass-border rounded-xl pl-9 rtl:pr-9 pr-3 rtl:pl-3 py-2 text-xs text-text-main placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  {historySearch && (
                    <button 
                      onClick={() => setHistorySearch("")}
                      className="absolute right-2.5 rtl:left-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-main"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="p-6 overflow-y-auto divide-y divide-glass-border/50">
                {isLoadingHistory && (
                  <div className="py-8 text-center text-xs text-text-muted">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-primary dark:text-accent" />
                    Loading database audit records...
                  </div>
                )}
                {!isLoadingHistory && filteredHistory.map((h) => (
                  <div key={h.id} className="py-3.5 flex items-center justify-between gap-4 hover:bg-surface/30 px-3 rounded-xl transition-colors">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-text-main truncate flex items-center gap-2">
                        <span>{h.project_name}</span>
                        <span className="text-[10px] font-mono text-text-muted px-1.5 py-0.5 rounded bg-surface border border-glass-border">
                          {h.id}
                        </span>
                      </div>
                      <div className="text-xs text-text-muted flex items-center gap-2 mt-1">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{h.timestamp ? new Date(h.timestamp).toLocaleString() : 'Recent Record'}</span>
                        <span>•</span>
                        <span>{h.total_files} {t("all_files")}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className={`text-sm font-bold ${h.overall_similarity >= 65 ? 'text-red-600 dark:text-red-400' : h.overall_similarity >= 25 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                        {h.overall_similarity}%
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                        h.verdict === 'SAFE' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
                      }`}>
                        {h.verdict}
                      </span>
                      <button
                        onClick={() => {
                          setIsHistoryOpen(false);
                          navigate(`/scan?project=${encodeURIComponent(h.project_name || h.id)}`);
                        }}
                        className="px-2.5 py-1.5 rounded-lg bg-accent text-accent-text font-medium text-xs flex items-center gap-1 shadow-sm transition-all hover:scale-105"
                        title={t("inspect_report")}
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                      <button 
                        onClick={() => handleDeleteHistoryReport(h.id)}
                        className="btn-danger-icon"
                        title={t("delete_record")}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {!isLoadingHistory && filteredHistory.length === 0 && (
                  <div className="py-12 text-center text-xs text-text-muted">
                    {t("no_history_records")}
                  </div>
                )}
              </div>
            </motion.div>
          </>
        , document.body)}
      </AnimatePresence>
    </div>
  );
}

export default Plagiarism;
