import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { GitBranch, Globe, FileText, ShieldCheck, Search, RefreshCw, Info, Edit3, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { useScanStore } from "../../lib/scanStore";
import { GitRepoScanPayload, plagiarismApi } from "../../lib/api";
import { handleStreamSession } from "./hooks/useScanStream";

function extractRepoNameFromUrl(url: string): string {
  try {
    const clean = url.trim().replace(/\.git$/, "").replace(/\/+$/, "");
    const parts = clean.split("/");
    return parts[parts.length - 1] || "";
  } catch {
    return "";
  }
}

export function GitScanSection() {
  const { t } = useTranslation();
  
  // Git Repository Intake State
  const [gitRepoUrl, setGitRepoUrl] = useState<string>("");
  const [gitBranch, setGitBranch] = useState<string>("main");
  const [gitAccessToken, setGitAccessToken] = useState<string>("");
  const [gitProjectTitle, setGitProjectTitle] = useState<string>("");
  const [showCustomTitle, setShowCustomTitle] = useState(false);

  const isScanning = useScanStore((s) => s.isScanning);
  const scanSource = useScanStore((s) => s.scanSource);
  const isIntakeScanning = isScanning && (scanSource === "intake" || !scanSource);

  const autoDetectedName = useMemo(() => extractRepoNameFromUrl(gitRepoUrl), [gitRepoUrl]);
  const effectiveProjectName = gitProjectTitle.trim() || autoDetectedName || "git_project";

  // Start Git Repository Scan with Real-Time Streaming
  const startGitScan = async () => {
    if (!gitRepoUrl.trim()) {
      toast.error(t("git_repo_url") + " is required.");
      return;
    }

    const cleanProjectName = effectiveProjectName;

    // Reset previous terminal logs
    useScanStore.getState().resetScan();

    const controller = new AbortController();
    useScanStore.getState().setAbortController(controller);
    useScanStore.getState().startScan(cleanProjectName, 'intake');

    const initialLogs = [
      `[${new Date().toLocaleTimeString()}] [GIT] Connecting to remote repository: ${gitRepoUrl.trim()}`,
      `[${new Date().toLocaleTimeString()}] [GIT] Target Branch: ${gitBranch || 'main'}`,
      `[${new Date().toLocaleTimeString()}] [SECURITY] Isolated ephemeral sandbox allocated.`,
    ];
    initialLogs.forEach((log) => useScanStore.getState().appendLog(log));

    // Auto-populate academic metadata from authenticated user profile
    const userStr = localStorage.getItem("user_data") || localStorage.getItem("user");
    let userData: any = {};
    try { if (userStr) userData = JSON.parse(userStr); } catch {}

    const payload: GitRepoScanPayload = {
      repo_url: gitRepoUrl.trim(),
      branch: gitBranch.trim() || "main",
      access_token: gitAccessToken.trim() || undefined,
      project_name: cleanProjectName,
      title: cleanProjectName,
      department: userData.department_name || userData.department_id || "Computer Engineering",
      year: new Date().getFullYear(),
      university: userData.university_name || "Sana'a University",
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
      <div className="glass-card !p-6 space-y-6 rounded-2xl border border-border shadow-sm">
        <div className="flex items-start gap-4">
          <div className="p-3.5 bg-primary/10 border border-primary/20 rounded-2xl text-primary shrink-0">
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
            <label className="text-xs font-semibold text-text-main flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-primary dark:text-accent" />
                {t("git_repo_url")} <span className="text-rose-500">*</span>
              </span>
              {autoDetectedName && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-accent/20 text-accent-text border border-accent/30">
                  <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                  Auto: {autoDetectedName}
                </span>
              )}
            </label>
            <input 
              type="text"
              placeholder={t("git_repo_url_placeholder")}
              value={gitRepoUrl}
              onChange={(e) => setGitRepoUrl(e.target.value)}
              className="input-field w-full font-mono text-xs py-2.5"
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
              className="input-field w-full font-mono text-xs py-2.5"
            />
          </div>

          {/* Access Token (Optional) */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-text-muted flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
              {t("git_token_label")}
            </label>
            <input 
              type="password"
              autoComplete="new-password"
              placeholder={t("git_token_placeholder")}
              value={gitAccessToken}
              onChange={(e) => setGitAccessToken(e.target.value)}
              className="input-field w-full font-mono text-xs py-2.5"
            />
          </div>

          {/* Optional Title Override Toggle */}
          <div className="md:col-span-2 pt-1">
            {!showCustomTitle ? (
              <button
                type="button"
                onClick={() => setShowCustomTitle(true)}
                className="text-xs text-text-muted hover:text-text-main flex items-center gap-1.5 transition-colors"
              >
                <Edit3 className="w-3 h-3 text-primary" />
                <span>Specify Custom Project / Thesis Title (Optional)</span>
              </button>
            ) : (
              <div className="space-y-1.5 p-3.5 rounded-xl bg-surface/50 border border-border/60">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-main flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-primary" />
                    Custom Project / Thesis Title
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setShowCustomTitle(false);
                      setGitProjectTitle("");
                    }}
                    className="text-[11px] text-text-muted hover:text-text-main"
                  >
                    Reset to auto-detected
                  </button>
                </div>
                <input 
                  type="text"
                  placeholder={autoDetectedName || "e.g. Autonomous SLAM Quadrotor"}
                  value={gitProjectTitle}
                  onChange={(e) => setGitProjectTitle(e.target.value)}
                  className="input-field w-full text-xs py-2"
                />
              </div>
            )}
          </div>
        </div>

        {/* Unified Card Footer: Security Gate info on start, Action CTA on end */}
        <div className="pt-4 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <Info className="w-4 h-4 text-primary shrink-0" />
            <span>Shallow clone depth=1 • Ephemeral sandbox • Safe indexing</span>
          </div>

          <button 
            onClick={startGitScan}
            disabled={isIntakeScanning || !gitRepoUrl.trim()}
            className="btn-primary w-full sm:w-auto px-6 py-2.5 text-sm font-semibold shrink-0"
          >
            {isIntakeScanning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                {t("processing_files")}
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                {t("clone_index_repo")}
              </>
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
