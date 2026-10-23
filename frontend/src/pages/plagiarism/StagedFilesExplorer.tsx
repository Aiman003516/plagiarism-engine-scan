import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, X, FileCode2, FileText, TerminalSquare,
  ShieldCheck, FileArchive, FilePlus, ChevronDown, ChevronUp, HardDrive
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { UploadedFileInfo } from "../../lib/scanStore";
import { formatFileSize } from "./fileConstants";

interface StagedFilesExplorerProps {
  uploadedFiles: UploadedFileInfo[];
  bloatFilteredCount: number;
  totalStagedSize: number;
  stagedCodeCount: number;
  stagedDocCount: number;
  stagedArchiveCount: number;
  stagedLoc: number;
  showExplorer: boolean;
  setShowExplorer: (v: boolean) => void;
  stagedCategory: "all" | "code" | "text" | "archive";
  setStagedCategory: (v: "all" | "code" | "text" | "archive") => void;
  stagedSearch: string;
  setStagedSearch: (v: string) => void;
  filteredStagedFiles: UploadedFileInfo[];
  removeStagedFile: (id: string) => void;
}

export function StagedFilesExplorer({
  uploadedFiles,
  bloatFilteredCount,
  totalStagedSize,
  stagedCodeCount,
  stagedDocCount,
  stagedArchiveCount,
  stagedLoc,
  showExplorer,
  setShowExplorer,
  stagedCategory,
  setStagedCategory,
  stagedSearch,
  setStagedSearch,
  filteredStagedFiles,
  removeStagedFile,
}: StagedFilesExplorerProps) {
  const { t } = useTranslation();

  if (uploadedFiles.length === 0 && bloatFilteredCount === 0) {
    return null;
  }

  return (
    <>
      <div className="mt-5 pt-5 border-t border-glass-border/40 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-xs font-semibold text-text-muted flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
              {t("intake_progress_title")}:
            </span>

            {bloatFilteredCount > 0 && (
              <span className="px-2.5 py-1 rounded-full bg-text-muted/10 border border-text-muted/20 text-text-muted text-xs font-medium">
                🛡️ {bloatFilteredCount} {t("intake_bloat_eliminated")}
              </span>
            )}

            <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
              ⚡ {uploadedFiles.length} {t("intake_core_staged")}
            </span>

            <span className="px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium">
              📏 {formatFileSize(totalStagedSize)} <span className="opacity-70 font-normal ml-1">(uploaded archives)</span>
            </span>
          </div>

          <button
            onClick={() => setShowExplorer(!showExplorer)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-surface border border-glass-border hover:bg-surface-hover text-text-main text-xs font-medium transition-colors"
          >
            <HardDrive className="w-3.5 h-3.5 text-primary dark:text-accent" />
            {t("staged_files_header")} ({uploadedFiles.length})
            {showExplorer ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs">
            <FileCode2 className="w-3.5 h-3.5" />
            {stagedCodeCount} {t("code_files")}
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs">
            <FileText className="w-3.5 h-3.5" />
            {stagedDocCount} {t("doc_files")}
          </div>
          {stagedArchiveCount > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-accent/10 border border-accent/20 text-accent-text text-xs">
              <FileArchive className="w-3.5 h-3.5" />
              {stagedArchiveCount} {t("archive_files")}
            </div>
          )}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs">
            <TerminalSquare className="w-3.5 h-3.5" />
            {stagedLoc.toLocaleString()} {t("loc_staged_metric")}
          </div>
        </div>
      </div>

      <AnimatePresence>
        {showExplorer && uploadedFiles.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-5 pt-5 border-t border-glass-border/40 overflow-hidden"
          >
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-3">
              <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
                <button
                  onClick={() => setStagedCategory("all")}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "all" ? "bg-accent text-accent-text" : "bg-surface text-text-muted hover:text-text-main"}`}
                >
                  {t("all_files")} ({uploadedFiles.length})
                </button>
                <button
                  onClick={() => setStagedCategory("code")}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "code" ? "bg-primary text-primary-text" : "bg-surface text-text-muted hover:text-text-main"}`}
                >
                  {t("code_files")} ({stagedCodeCount})
                </button>
                <button
                  onClick={() => setStagedCategory("text")}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "text" ? "bg-amber-600 text-white" : "bg-surface text-text-muted hover:text-text-main"}`}
                >
                  {t("doc_files")} ({stagedDocCount})
                </button>
                {stagedArchiveCount > 0 && (
                  <button
                    onClick={() => setStagedCategory("archive")}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "archive" ? "bg-accent text-accent-text" : "bg-surface text-text-muted hover:text-text-main"}`}
                  >
                    {t("archive_files")} ({stagedArchiveCount})
                  </button>
                )}
              </div>

              <div className="relative w-full sm:w-72">
                <Search className="absolute left-3 rtl:right-3 rtl:left-auto top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
                <input
                  type="text"
                  placeholder={t("search_staged_files")}
                  value={stagedSearch}
                  onChange={(e) => setStagedSearch(e.target.value)}
                  className="w-full bg-surface/50 border border-glass-border rounded-lg pl-9 pr-3 rtl:pr-9 rtl:pl-3 py-1.5 text-xs text-text-main placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
            </div>

            <div className="max-h-56 overflow-y-auto rounded-xl border border-glass-border divide-y divide-glass-border/40 bg-surface/20">
              {filteredStagedFiles.map((file) => (
                <div key={file.id} className="p-2.5 px-4 flex items-center justify-between hover:bg-surface/40 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    {file.type === "code" && <FileCode2 className="w-4 h-4 text-primary shrink-0" />}
                    {file.type === "text" && <FileText className="w-4 h-4 text-amber-400 shrink-0" />}
                    {file.type === "archive" && <FileArchive className="w-4 h-4 text-accent-text shrink-0" />}
                    {file.type === "other" && <FilePlus className="w-4 h-4 text-text-muted shrink-0" />}
                    <span className="text-xs font-mono text-text-main truncate">{file.path}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-[11px] text-text-muted font-mono">{formatFileSize(file.size)}</span>
                    <button
                      onClick={() => removeStagedFile(file.id)}
                      className="text-text-muted hover:text-red-500 dark:hover:text-red-400 p-1 rounded transition-colors"
                      title={t("remove_file")}
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
              {filteredStagedFiles.length === 0 && (
                <div className="p-6 text-center text-xs text-text-muted">
                  {t("no_files_staged")}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
