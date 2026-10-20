import React, { useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Search, UploadCloud, Cpu, FileArchive, Trash2,
  FilePlus, RefreshCw
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useScanStore, UploadedFileInfo } from "../../lib/scanStore";
import { API_BASE_URL, plagiarismApi } from "../../lib/api";
import { readZipScanStream, handleStreamSession } from "./hooks/useScanStream";
import {
  CODE_EXTS, TEXT_EXTS, ARCHIVE_EXTS, IGNORE_PATTERNS,
  BINARY_EXTS, formatFileSize, traverseDirectoryEntry, policyExclusionReason
} from "./fileConstants";
import { StagedFilesExplorer } from "./StagedFilesExplorer";

export function UploadSection() {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const zipInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const projectName = useScanStore((s) => s.projectName);
  const uploadedFiles = useScanStore((s) => s.uploadedFiles);
  const [isDragging, setIsDragging] = useState(false);
  const isProcessingFiles = useScanStore((s) => s.isProcessingFiles);
  const isTraversing = useScanStore((s) => s.isTraversing);
  const totalFilesToProcess = useScanStore((s) => s.totalFilesToProcess);
  const processedFilesCount = useScanStore((s) => s.processedFilesCount);
  const processingPhase = useScanStore((s) => s.processingPhase);
  const isScanning = useScanStore((s) => s.isScanning);
  const bloatFilteredCount = useScanStore((s) => s.bloatFilteredCount);

  const [showExplorer, setShowExplorer] = useState(false);
  const [stagedSearch, setStagedSearch] = useState("");
  const [stagedCategory, setStagedCategory] = useState<"all" | "code" | "text" | "archive">("all");

  const processRawFiles = async (files: File[], customPaths?: string[]) => {
    useScanStore.getState().setProcessingState({
      isProcessing: true,
      total: files.length,
      processed: 0,
      phase: `Reading file content (0/${files.length.toLocaleString()})...`,
    });

    const newItems: UploadedFileInfo[] = [];
    let detectedProjectName = "";
    let localBloatCount = 0;
    let localInspectedCount = 0;

    const startTime = Date.now();
    const CHUNK_SIZE = 500;

    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      const chunk = files.slice(i, Math.min(i + CHUNK_SIZE, files.length));

      for (let j = 0; j < chunk.length; j++) {
        const file = chunk[j];
        const actualIndex = i + j;
        localInspectedCount++;
        const relativePath = customPaths?.[actualIndex] || (file as any).webkitRelativePath || file.name;
        const pathLower = relativePath.toLowerCase();

        if (relativePath.includes("/")) {
          const root = relativePath.split("/")[0];
          if (!detectedProjectName && root && !IGNORE_PATTERNS.includes(root)) {
            detectedProjectName = root;
          }
        }

        const isIgnored = IGNORE_PATTERNS.some(p =>
          pathLower.includes(`/${p}/`) || pathLower.startsWith(`${p}/`) || pathLower.includes(`\\${p}\\`)
        );
        if (isIgnored) {
          localBloatCount++;
          continue;
        }

        const ext = file.name.split(".").pop()?.toLowerCase() || "";
        if (BINARY_EXTS.has(ext) || policyExclusionReason(file.name)) {
          localBloatCount++;
          continue;
        }

        let fileType: "code" | "text" | "archive" | "other" = "other";
        if (CODE_EXTS.has(ext)) {
          fileType = "code";
        } else if (TEXT_EXTS.has(ext)) {
          fileType = "text";
        } else if (ARCHIVE_EXTS.has(ext)) {
          fileType = "archive";
        }

        let contentText: string | undefined = undefined;
        if ((fileType === "code" || fileType === "text") && file.size < 10 * 1024 * 1024) {
          try {
            contentText = await file.text();
          } catch {
            // Binary fallback
          }
        }

        newItems.push({
          id: `${relativePath}_${file.size}_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
          path: relativePath,
          name: file.name,
          size: file.size,
          type: fileType,
          content: contentText,
          file,
        });
      }

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      useScanStore.getState().setProcessingState({
        processed: i + chunk.length,
        phase: `Reading file content (${(i + chunk.length).toLocaleString()}/${files.length.toLocaleString()}) — ${elapsed}s elapsed`,
      });
      await new Promise(r => setTimeout(r, 0));
    }

    const intakeState = useScanStore.getState();
    useScanStore.getState().setBloatStats(intakeState.bloatFilteredCount + localBloatCount, intakeState.inspectedTotalNodes + localInspectedCount);

    useScanStore.getState().setUploadedFiles((prev) => {
      const existingPaths = new Set(prev.map(p => p.path));
      const filteredNew = newItems.filter(item => !existingPaths.has(item.path));
      return [...prev, ...filteredNew];
    });

    if (detectedProjectName && !projectName) {
      useScanStore.getState().setProjectName(detectedProjectName);
    } else if (files.length === 1 && !projectName) {
      useScanStore.getState().setProjectName(files[0].name.replace(/\.[^/.]+$/, ""));
    }

    useScanStore.getState().setProcessingState({ isProcessing: false });
    if (newItems.length > 0) {
      setShowExplorer(true);
      toast.success(`${newItems.length} ${t("total_staged_stats")}`);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processRawFiles(Array.from(e.target.files));
      e.target.value = "";
    }
  };

  const handleZipSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processRawFiles(Array.from(e.target.files));
      e.target.value = "";
    }
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    useScanStore.getState().setProcessingState({ isTraversing: true, phase: "Scanning directory structure..." });

    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      const filePromises: Promise<{ file: File; path: string }[]>[] = [];

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (typeof item.webkitGetAsEntry === "function") {
          const entry = item.webkitGetAsEntry();
          if (entry) {
            filePromises.push(traverseDirectoryEntry(entry));
          }
        }
      }

      if (filePromises.length > 0) {
        const results = await Promise.all(filePromises);
        const flattened = results.flat();
        const files = flattened.map(f => f.file);
        const paths = flattened.map(f => f.path);

        useScanStore.getState().setProcessingState({ isTraversing: false });

        if (files.length > 0) {
          processRawFiles(files, paths);
          return;
        }
      }
    }

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processRawFiles(Array.from(e.dataTransfer.files));
    }

    useScanStore.getState().setProcessingState({ isTraversing: false });
  };

  const removeStagedFile = (id: string) => {
    useScanStore.getState().setUploadedFiles((prev) => prev.filter(f => f.id !== id));
  };

  const clearUpload = () => {
    useScanStore.getState().setUploadedFiles([]);
    useScanStore.getState().setProjectName("");
    useScanStore.getState().setBloatStats(0, 0);
    setShowExplorer(false);
    toast.success(t("clear_all"));
  };

  const stagedCodeCount = uploadedFiles.filter(f => f.type === "code").length;
  const stagedDocCount = uploadedFiles.filter(f => f.type === "text").length;
  const stagedArchiveCount = uploadedFiles.filter(f => f.type === "archive").length;
  const stagedLoc = uploadedFiles
    .filter(f => f.type === "code" && f.content)
    .reduce((acc, f) => acc + (f.content ? f.content.split("\n").length : 0), 0);
  const totalStagedSize = uploadedFiles.reduce((acc, f) => acc + f.size, 0);

  const filteredStagedFiles = uploadedFiles.filter(f => {
    const matchesSearch = f.path.toLowerCase().includes(stagedSearch.toLowerCase()) || f.name.toLowerCase().includes(stagedSearch.toLowerCase());
    const matchesCategory = stagedCategory === "all" || f.type === stagedCategory;
    return matchesSearch && matchesCategory;
  });

  const startDirectScan = async () => {
    if (isScanning) return;
    if (uploadedFiles.length === 0) {
      toast.error(t("no_files_staged"));
      return;
    }

    const archives = uploadedFiles.filter(f => f.type === "archive");
    const isZipFlow = uploadedFiles.length === 1 && archives.length === 1;

    if (archives.length > 0 && !isZipFlow) {
      toast.success(t("nested_archives_ignored", "Nested archives detected and ignored. Scanning source files."), { icon: "ℹ️" });
    } else if (archives.length > 0 && isZipFlow) {
      if (!archives[0].name.toLowerCase().endsWith(".zip")) {
        toast.error(t("only_zip_supported", "Only .zip archives are supported."));
        return;
      }
    }

    const zipFile = isZipFlow ? archives[0] : undefined;
    const activeProjectName = projectName.trim() || (uploadedFiles[0].path.includes("/") ? uploadedFiles[0].path.split("/")[0] : "Intake_Project");
    const appendLog = (text: string) => useScanStore.getState().appendLog(text);
    const appendServerLog = (text: string) => useScanStore.getState().noteServerLog(text);
    const onComplete = (result?: any) => {
      appendLog(`[${new Date().toLocaleTimeString()}] [COMPLETED] ✅ Scan completed for ${activeProjectName}.`);
      if (result) {
        useScanStore.getState().completeScan(result);
      }
      toast.success(t("intake_progress_title") + " ✓");
    };
    const onError = (message: string) => {
      appendLog(`[${new Date().toLocaleTimeString()}] [ERROR] ❌ ${message}`);
      useScanStore.getState().failScan(message);
      toast.error(message);
    };

    const controller = new AbortController();
    useScanStore.getState().setAbortController(controller);
    useScanStore.getState().startScan(activeProjectName, 'intake');
    appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Staging ${uploadedFiles.length} files (${formatFileSize(totalStagedSize)})`);
    appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Checking project: ${activeProjectName}`);

    try {
      const res = await fetch(`${API_BASE_URL}/api/plagiarism/projects/check?names=${encodeURIComponent(activeProjectName)}`).catch(() => null);
      if (res?.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          throw new Error(`Project "${activeProjectName}" already exists in the database. Skipping duplicate.`);
        }
      }

      if (zipFile) {
        const formData = new FormData();
        formData.append("project_name", activeProjectName);
        formData.append("scan_type", "ZIP Archive Scan");
        formData.append("file", zipFile.file, zipFile.name);

        appendLog(`[${new Date().toLocaleTimeString()}] [UPLOAD] Sending ${zipFile.name} (${formatFileSize(zipFile.size)})...`);
        appendLog("[STATUS] Waiting for backend logs. This endpoint may buffer logs until processing finishes.");
        const token = localStorage.getItem("auth_token");
        const headers: Record<string, string> = { Accept: "text/event-stream" };
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const response = await fetch(`${API_BASE_URL}/api/plagiarism/upload-zip-stream`, {
          method: "POST",
          headers,
          body: formData,
          signal: controller.signal,
        });
        const result = await readZipScanStream(response, appendServerLog, handleStreamSession);
        if (result) {
          onComplete(result);
        }
      } else {
        appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Code files: ${stagedCodeCount}, Documents: ${stagedDocCount}, Total LOC: ${stagedLoc}`);
        const payloadFiles = uploadedFiles
          .filter(f => f.type !== "other" && f.type !== "archive")
          .map(f => ({
            path: f.path,
            content: f.content || "",
            file_type: f.type,
            file: f.file,
          }));

        if (payloadFiles.length === 0) {
          throw new Error(
            t("no_scannable_source_files", "No scannable source files remain after ignoring nested archives.")
          );
        }

        await plagiarismApi.uploadAndScanStream(
          activeProjectName,
          payloadFiles,
          "Direct Upload Project Scan",
          appendServerLog,
          onComplete,
          onError,
          controller.signal,
          handleStreamSession
        );
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to upload and scan the project.");
      useScanStore.setState({ isScanning: false });
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      {/* Hidden file inputs */}
      <input type="file" ref={fileInputRef} onChange={handleFileSelect} multiple className="hidden" />
      <input type="file" ref={zipInputRef} onChange={handleZipSelect} accept=".zip" className="hidden" />
      <input
        type="file"
        ref={folderInputRef}
        onChange={handleFileSelect}
        // @ts-ignore - webkitdirectory is non-standard but supported
        webkitdirectory=""
        directory=""
        className="hidden"
      />

      <div className="glass-card !p-6 relative overflow-hidden">
        <div
          className={`border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-10 transition-all duration-300 cursor-pointer ${
            isDragging
              ? "border-accent bg-accent/10 scale-[1.01] shadow-[0_0_30px_rgba(249,115,22,0.2)]"
              : (isProcessingFiles || isTraversing)
              ? "border-accent/50 bg-accent/5"
              : "border-glass-border bg-surface/20 hover:border-accent/60 hover:bg-surface/30"
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(isProcessingFiles || isTraversing) ? undefined : handleDrop}
          onClick={(isProcessingFiles || isTraversing) ? undefined : () => zipInputRef.current?.click()}
        >
          {(isProcessingFiles || isTraversing) ? (
            <div className="flex flex-col items-center w-full max-w-md animate-in fade-in zoom-in duration-300">
              <div className="w-20 h-20 rounded-3xl bg-surface border border-glass-border flex items-center justify-center mb-4 shadow-2xl">
                <RefreshCw className="w-10 h-10 text-primary dark:text-accent animate-spin" />
              </div>
              <h2 className="text-xl font-bold text-text-main text-center mb-2">
                {processingPhase || t("processing_files", "Processing files...")}
              </h2>

              {totalFilesToProcess > 0 && (
                <div className="w-full mt-4 space-y-2">
                  <div className="flex justify-between text-xs font-mono text-text-muted">
                    <span>{processedFilesCount} / {totalFilesToProcess}</span>
                    <span>{Math.round((processedFilesCount / totalFilesToProcess) * 100)}%</span>
                  </div>
                  <div className="h-2.5 w-full bg-text-muted/15 dark:bg-slate-800 rounded-full overflow-hidden border border-glass-border dark:border-slate-700">
                    <div
                      className="h-full bg-gradient-to-r from-accent to-primary-hover rounded-full shadow-[0_0_10px_rgba(255,214,102,0.55)] transition-all duration-300 ease-out"
                      style={{ width: `${(processedFilesCount / totalFilesToProcess) * 100}%` }}
                    ></div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="w-20 h-20 rounded-3xl bg-surface border border-glass-border flex items-center justify-center mb-4 shadow-2xl group">
                <UploadCloud className={`w-10 h-10 transition-transform group-hover:scale-110 ${isDragging ? "text-primary dark:text-accent" : "text-text-muted"}`} />
              </div>

              <h2 className="text-xl font-bold text-text-main text-center">
                {t("unified_upload_title")}
              </h2>
              <p className="text-xs text-text-muted mt-2 mb-6 text-center max-w-xl leading-relaxed">
                {t("unified_upload_sub")}
              </p>

              <div className="w-full max-w-sm mb-4" onClick={(e) => e.stopPropagation()}>
                <input
                  type="text"
                  placeholder="Project Name (e.g., Spring2026_Final)"
                  className="w-full bg-surface border border-glass-border rounded-xl px-4 py-2.5 text-sm text-text-main focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 transition-all placeholder:text-text-muted/50"
                  value={projectName}
                  onChange={(e) => useScanStore.getState().setProjectName(e.target.value)}
                />
              </div>

              <div
                className="flex flex-wrap items-center justify-center gap-3 z-10"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isProcessingFiles}
                  className="bg-surface hover:bg-surface-hover border border-glass-border text-text-main font-semibold px-4 py-2.5 rounded-xl flex items-center gap-2 text-xs transition-all shadow-sm active:scale-95"
                >
                  <FilePlus className="w-4 h-4 text-primary" />
                  {t("browse_files")}
                </button>

                <button
                  onClick={() => folderInputRef.current?.click()}
                  disabled={isProcessingFiles}
                  className="bg-surface hover:bg-surface-hover border border-glass-border text-text-main font-semibold px-4 py-2.5 rounded-xl flex items-center gap-2 text-xs transition-all shadow-sm active:scale-95"
                >
                  <FilePlus className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />
                  {t("browse_folders")}
                </button>

                <button
                  onClick={() => zipInputRef.current?.click()}
                  disabled={isProcessingFiles}
                  className="bg-surface hover:bg-surface-hover border border-glass-border text-text-main font-semibold px-4 py-2.5 rounded-xl flex items-center gap-2 text-xs transition-all shadow-sm active:scale-95"
                >
                  <FileArchive className="w-4 h-4 text-accent-text" />
                  {t("browse_archives")}
                </button>
              </div>
            </>
          )}
        </div>

        <StagedFilesExplorer
          uploadedFiles={uploadedFiles}
          bloatFilteredCount={bloatFilteredCount}
          totalStagedSize={totalStagedSize}
          stagedCodeCount={stagedCodeCount}
          stagedDocCount={stagedDocCount}
          stagedArchiveCount={stagedArchiveCount}
          stagedLoc={stagedLoc}
          showExplorer={showExplorer}
          setShowExplorer={setShowExplorer}
          stagedCategory={stagedCategory}
          setStagedCategory={setStagedCategory}
          stagedSearch={stagedSearch}
          setStagedSearch={setStagedSearch}
          filteredStagedFiles={filteredStagedFiles}
          removeStagedFile={removeStagedFile}
        />
      </div>

      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 glass-card !p-5">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-accent/15 rounded-xl border border-accent/30 text-primary dark:text-accent">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-main">{t("codebert_title")} & {t("nlp_title")}</h3>
            <p className="text-xs text-text-muted">{t("nat_registry_active")}</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
          {!isScanning && uploadedFiles.length > 0 && (
            <button
              onClick={clearUpload}
              className="btn-danger w-full sm:w-auto px-6 py-3"
            >
              <Trash2 className="w-4 h-4" />
              {t("clear_uploads", "Clear Uploads")}
            </button>
          )}

          <button
            onClick={startDirectScan}
            disabled={isScanning || isProcessingFiles || isTraversing || uploadedFiles.length === 0}
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
                {t("upload_index_project")}
              </>
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}
