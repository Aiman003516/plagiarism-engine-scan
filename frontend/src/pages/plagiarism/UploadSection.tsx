import React, { useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Search, UploadCloud, Cpu, FileArchive, Trash2,
  FilePlus, RefreshCw, AlertTriangle, ChevronDown, ChevronUp,
  BookOpen, Building, Calendar, GraduationCap, X
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
  const scanSource = useScanStore((s) => s.scanSource);
  const scanError = useScanStore((s) => s.scanError);
  const isIntakeScanning = isScanning && (scanSource === "intake" || !scanSource);
  const bloatFilteredCount = useScanStore((s) => s.bloatFilteredCount);

  // Project Academic Metadata State (Pre-populated from user profile)
  const [metaTitle, setMetaTitle] = useState("");
  const [metaDepartment, setMetaDepartment] = useState(() => {
    try {
      const u = JSON.parse(localStorage.getItem("user_data") || "{}");
      return u.department_name || u.department_id || "Computer Engineering";
    } catch {
      return "Computer Engineering";
    }
  });
  const [metaYear, setMetaYear] = useState<string>(new Date().getFullYear().toString());
  const [metaUniversity, setMetaUniversity] = useState(() => {
    try {
      const u = JSON.parse(localStorage.getItem("user_data") || "{}");
      return u.university_name || "Baghdad University";
    } catch {
      return "Baghdad University";
    }
  });
  const [metaAbstract, setMetaAbstract] = useState("");
  const [showMetadata, setShowMetadata] = useState(false);

  const [showExplorer, setShowExplorer] = useState(false);
  const [stagedSearch, setStagedSearch] = useState("");
  const [stagedCategory, setStagedCategory] = useState<"all" | "code" | "text" | "archive">("all");

  const processRawFiles = async (files: File[], customPaths?: string[]) => {
    // Wipe previous live scan stream logs when staging new files for fresh intake/scan
    useScanStore.getState().resetScan();

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

    if (detectedProjectName) {
      useScanStore.getState().setProjectName(detectedProjectName);
    } else if (files.length === 1) {
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
    if (isIntakeScanning) return;
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
        if (metaTitle.trim()) formData.append("title", metaTitle.trim());
        if (metaAbstract.trim()) formData.append("abstract", metaAbstract.trim());
        if (metaDepartment.trim()) formData.append("department", metaDepartment.trim());
        if (metaYear.trim()) formData.append("year", metaYear.trim());
        if (metaUniversity.trim()) formData.append("university", metaUniversity.trim());

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
          handleStreamSession,
          {
            title: metaTitle.trim() || undefined,
            abstract: metaAbstract.trim() || undefined,
            department: metaDepartment.trim() || undefined,
            year: metaYear.trim() || undefined,
            university: metaUniversity.trim() || undefined,
          }
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

      {/* Intake-Scoped Error / Duplicate Notice */}
      {scanError && (scanSource === "intake" || !scanSource) && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-600 dark:text-red-400 flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5 text-red-500" />
            <div>
              <h4 className="font-bold text-sm">Intake Notice</h4>
              <p className="text-xs mt-0.5 leading-relaxed">{scanError}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => useScanStore.getState().failScan("")}
            className="text-text-muted hover:text-text-main p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* UNIFIED SUBMISSION & INDEXING CONTROL DOCK */}
      <div className="glass-card !p-5 space-y-4">
        {/* Dock Header: Engine Status & Metadata Toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-glass-border">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 rounded-xl border border-primary/20 text-primary flex-shrink-0">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-text-main flex items-center gap-2">
                <span>{t("codebert_title")} & {t("nlp_title")}</span>
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  Active
                </span>
              </h4>
              <p className="text-xs text-text-muted">{t("nat_registry_active")}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setShowMetadata(!showMetadata)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-glass-border bg-surface/50 hover:bg-surface text-xs font-semibold text-text-muted hover:text-text-main transition-colors self-start sm:self-auto"
          >
            <BookOpen className="w-3.5 h-3.5 text-primary" />
            <span>Academic Metadata</span>
            {showMetadata ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Optional Academic Metadata Drawer */}
        {showMetadata && (
          <div className="p-4 rounded-xl bg-surface/40 border border-glass-border space-y-3 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-primary" /> Full Project Title
                </label>
                <input
                  type="text"
                  placeholder="e.g. Autonomous Robotic Navigation Using Deep RL"
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                  className="w-full bg-surface border border-glass-border rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-primary/50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1.5">
                  <GraduationCap className="w-3.5 h-3.5 text-primary" /> University / Institution
                </label>
                <input
                  type="text"
                  placeholder="e.g. Sana'a University"
                  value={metaUniversity}
                  onChange={(e) => setMetaUniversity(e.target.value)}
                  className="w-full bg-surface border border-glass-border rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-primary/50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1.5">
                  <Building className="w-3.5 h-3.5 text-primary" /> Department
                </label>
                <input
                  type="text"
                  placeholder="e.g. Computer Science & AI"
                  value={metaDepartment}
                  onChange={(e) => setMetaDepartment(e.target.value)}
                  className="w-full bg-surface border border-glass-border rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-primary/50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1 flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-primary" /> Academic Year
                </label>
                <input
                  type="number"
                  placeholder="2026"
                  value={metaYear}
                  onChange={(e) => setMetaYear(e.target.value)}
                  className="w-full bg-surface border border-glass-border rounded-lg px-3 py-2 text-xs text-text-main focus:outline-none focus:border-primary/50"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1">
                Abstract / Executive Summary
              </label>
              <textarea
                rows={3}
                placeholder="Briefly describe the project goals, methodologies, findings, or algorithms..."
                value={metaAbstract}
                onChange={(e) => setMetaAbstract(e.target.value)}
                className="w-full bg-surface border border-glass-border rounded-lg p-3 text-xs text-text-main focus:outline-none focus:border-primary/50 resize-none"
              />
            </div>
          </div>
        )}

        {/* Dock Bottom Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-1">
          <div className="text-xs text-text-muted">
            {uploadedFiles.length > 0 ? (
              <span className="font-medium text-text-main">
                {uploadedFiles.length} file{uploadedFiles.length === 1 ? "" : "s"} staged ({Math.round(totalStagedSize / 1024)} KB) • Ready for indexing
              </span>
            ) : (
              <span>Stage project files or archives above to begin indexing.</span>
            )}
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
            {!isScanning && uploadedFiles.length > 0 && (
              <button
                type="button"
                onClick={clearUpload}
                className="btn-danger w-full sm:w-auto px-5 py-2.5 text-xs font-semibold rounded-xl"
              >
                <Trash2 className="w-4 h-4" />
                {t("clear_uploads", "Clear Uploads")}
              </button>
            )}

            <button
              type="button"
              onClick={startDirectScan}
              disabled={isIntakeScanning || isProcessingFiles || isTraversing || uploadedFiles.length === 0}
              className="w-full sm:w-auto bg-primary hover:bg-primary-hover text-primary-text font-bold text-sm rounded-xl px-7 py-3 shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 transform active:scale-95 disabled:opacity-40 disabled:pointer-events-none"
            >
              {isIntakeScanning ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  {t("processing_files")}
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  {t("upload_index_project")}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
