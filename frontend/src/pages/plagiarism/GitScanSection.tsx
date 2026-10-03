import React, { useState } from "react";
import { motion } from "framer-motion";
import { GitBranch, Globe, FileText, ShieldCheck, Code2, Search, RefreshCw, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { useScanStore } from "../../lib/scanStore";
import { GitRepoScanPayload, plagiarismApi } from "../../lib/api";
import { handleStreamSession } from "./hooks/useScanStream";

export function GitScanSection() {
  const { t } = useTranslation();
  
  // Git Repository Intake State
  const [gitRepoUrl, setGitRepoUrl] = useState<string>("");
  const [gitBranch, setGitBranch] = useState<string>("main");
  const [gitAccessToken, setGitAccessToken] = useState<string>("");
  const [gitProjectTitle, setGitProjectTitle] = useState<string>("");

  const isScanning = useScanStore((s) => s.isScanning);

  // Start Git Repository Scan with Real-Time Streaming
  const startGitScan = async () => {
    if (!gitRepoUrl.trim()) {
      toast.error(t("git_repo_url") + " is required.");
      return;
    }

    const gitProjectName = gitProjectTitle.trim() || gitRepoUrl.trim();
    const controller = new AbortController();
    useScanStore.getState().setAbortController(controller);
    useScanStore.getState().startScan(gitProjectName);

    const initialLogs = [
      `[${new Date().toLocaleTimeString()}] [GIT] Connecting to remote repository: ${gitRepoUrl.trim()}`,
      `[${new Date().toLocaleTimeString()}] [GIT] Target Branch: ${gitBranch || 'main'}`,
      `[${new Date().toLocaleTimeString()}] [SECURITY] Isolated ephemeral sandbox allocated.`,
    ];
    initialLogs.forEach((log) => useScanStore.getState().appendLog(log));

    const payload: GitRepoScanPayload = {
      repo_url: gitRepoUrl.trim(),
      branch: gitBranch.trim() || "main",
      access_token: gitAccessToken.trim() || undefined,
      project_name: gitProjectTitle.trim() || undefined,
      scan_type: "Git Repository AI Integrity Scan"
    };

    try {
      await plagiarismApi.scanGitRepoStream(
        payload,
        (logText) => {
          useScanStore.getState().noteServerLog(logText);
        },
        (result) => {
          useScanStore.getState().completeScan(result);
          toast.success(t("intake_progress_title") + " ✓");
        },
        (errorMsg) => {
          useScanStore.getState().appendLog(`[${new Date().toLocaleTimeString()}] [ERROR] ❌ ${errorMsg}`);
          useScanStore.getState().failScan(errorMsg);
          toast.error(errorMsg);
        },
        controller.signal,
        handleStreamSession
      );
    } catch (error) {
      useScanStore.setState({ isScanning: false });
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      <div className="glass-card !p-6 space-y-6">
        <div className="flex items-start gap-4">
          <div className="p-3.5 bg-primary/10 border border-primary/20 rounded-2xl text-primary">
            <GitBranch className="w-7 h-7" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-text-main">{t("git_repo_card_title")}</h2>
            <p className="text-xs text-text-muted mt-1 leading-relaxed max-w-2xl">{t("git_repo_card_desc")}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Repo URL */}
          <div className="space-y-1.5 md:col-span-2">
            <label className="text-xs font-semibold text-text-main flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-primary dark:text-accent" />
              {t("git_repo_url")} <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            <input 
              type="text"
              placeholder={t("git_repo_url_placeholder")}
              value={gitRepoUrl}
              onChange={(e) => setGitRepoUrl(e.target.value)}
              className="w-full bg-surface/50 border border-glass-border rounded-xl px-4 py-2.5 text-sm text-text-main placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 font-mono"
            />
          </div>

          {/* Branch */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-text-main flex items-center gap-1.5">
              <GitBranch className="w-3.5 h-3.5 text-primary" />
              {t("git_branch")}
            </label>
            <input 
              type="text"
              placeholder="main"
              value={gitBranch}
              onChange={(e) => setGitBranch(e.target.value)}
              className="w-full bg-surface/50 border border-glass-border rounded-xl px-4 py-2.5 text-sm text-text-main placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 font-mono"
            />
          </div>

          {/* Project / Thesis Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-text-main flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />
              {t("git_project_name")}
            </label>
            <input 
              type="text"
              placeholder={t("git_project_name_placeholder")}
              value={gitProjectTitle}
              onChange={(e) => setGitProjectTitle(e.target.value)}
              className="w-full bg-surface/50 border border-glass-border rounded-xl px-4 py-2.5 text-sm text-text-main placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          {/* Access Token (Optional) */}
          <div className="space-y-1.5 md:col-span-2">
            <label className="text-xs font-semibold text-text-muted flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
              {t("git_token_label")}
            </label>
            <input 
              type="password"
              placeholder={t("git_token_placeholder")}
              value={gitAccessToken}
              onChange={(e) => setGitAccessToken(e.target.value)}
              className="w-full bg-surface/50 border border-glass-border rounded-xl px-4 py-2.5 text-sm text-text-main placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 font-mono"
            />
          </div>
        </div>

        {/* Ingestion Specs Note */}
        <div className="p-4 rounded-xl bg-surface/30 border border-glass-border flex items-center justify-between text-xs text-text-muted">
          <span className="flex items-center gap-2">
            <Info className="w-4 h-4 text-primary dark:text-accent shrink-0" />
            <span>Shallow Clone depth=1 • Automated .gitignore bloat exclusion • Ephemeral secure sandbox</span>
          </span>
          <span className="font-semibold text-emerald-600 dark:text-emerald-400">Security Gate: Active</span>
        </div>
      </div>

      {/* PRIMARY CTA FOR GIT SCAN */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 glass-card !p-5">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-primary/10 rounded-xl border border-primary/30 text-primary">
            <Code2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-main">{t("git_repo_card_title")}</h3>
            <p className="text-xs text-text-muted">{t("nat_registry_active")}</p>
          </div>
        </div>

        <button 
          onClick={startGitScan}
          disabled={isScanning || !gitRepoUrl.trim()}
          className="w-full sm:w-auto bg-primary hover:bg-primary-hover text-primary-text font-bold text-base rounded-xl px-8 py-3.5 shadow-lg hover:shadow-xl transition-all flex items-center justify-center gap-2.5 transform active:scale-95 disabled:opacity-40 disabled:pointer-events-none"
        >
          {isScanning ? (
            <>
              <RefreshCw className="w-5 h-5 animate-spin" />
              {t("processing_files")}
            </>
          ) : (
            <>
              <Search className="w-5 h-5" />
              {t("clone_index_repo")}
            </>
          )}
        </button>
      </div>
    </motion.div>
  );
}
