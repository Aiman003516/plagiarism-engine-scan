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
import { ScanHistoryModal } from "./ScanHistoryModal";

export function Plagiarism() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Re-attach scan stream if one is in flight
  useScanStreamReconnection("intake");

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

      <ScanProgress scope="intake" />

      {/* Database Scan History Modal */}
      <ScanHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectReport={(report) => {
          navigate(`/scan?project=${encodeURIComponent(report.project_name || report.id || "")}`);
        }}
      />
    </div>
  );
}

export default Plagiarism;
