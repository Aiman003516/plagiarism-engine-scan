import React, { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, X, UploadCloud, FileCode2, FileText,
  TerminalSquare, Cpu,
  Eye, ShieldAlert, Code2, ShieldCheck,
  History, Clock, FileArchive, Trash2,
  FilePlus, ChevronDown, ChevronUp, HardDrive,
  Copy, Download, Terminal, RefreshCw, GitBranch,
  Globe, Info,
} from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  plagiarismApi,
  PlagiarismHistoryItem,
  GitRepoScanPayload
} from "../lib/api";
import { useScanStore, UploadedFileInfo } from "../lib/scanStore";
// Supported file extension categories
const CODE_EXTS = new Set([
  "py", "js", "jsx", "ts", "tsx", "java", "c", "cpp", "h", "hpp", "cs", 
  "go", "rs", "php", "rb", "swift", "kt", "scala", "html", "css", "sql", "sh",
  "json", "yaml", "yml", "xml", "dart", "r", "m", "vue", "svelte"
]);

const TEXT_EXTS = new Set(["pdf", "docx", "doc", "txt", "md", "tex", "rtf", "odt"]);
const ARCHIVE_EXTS = new Set(["zip", "rar", "tar", "gz", "7z", "bz2"]);

// Silent background bloat filter patterns
const IGNORE_PATTERNS = [
  "node_modules", ".venv", "venv", "env", ".env", ".git", ".idea", ".vscode", 
  "__pycache__", "dist", "build", ".next", ".nuxt", ".cache", "bin", "obj", ".nuget",
  ".gradle", ".cargo", "site-packages", ".pytest_cache", ".mypy_cache", "vendor"
];

const BINARY_EXTS = new Set([
  "exe", "dll", "so", "dylib", "class", "pyc", "pyo", "pyd", "o", "a", "iso", "dmg", 
  "wasm", "bin", "pt", "pth", "h5", "hdf5", "onnx", "pkl", "pickle", "joblib",
  "mp4", "avi", "mov", "mkv", "mp3", "wav", "png", "jpg", "jpeg", "gif", "ico"
]);

// SSE events can span network chunks, including in the middle of a UTF-8 character.
async function readZipScanStream(response: Response, onLog: (text: string) => void): Promise<void> {
  if (!response.ok) {
    const detail = (await response.text()).trim();
    throw new Error(`ZIP upload failed (${response.status})${detail ? `: ${detail}` : "."}`);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("Expected an SSE response from the ZIP upload endpoint.");
  }
  if (!response.body) {
    throw new Error("Streaming responses are not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataLines: string[] = [];
  let completed = false;

  const dispatchEvent = () => {
    if (dataLines.length === 0) return;
    const data = dataLines.join("\n");
    dataLines = [];

    let event: { type?: string; text?: string; message?: string } | null;
    try {
      event = JSON.parse(data);
    } catch {
      throw new Error("Received an invalid JSON event from the ZIP scan stream.");
    }
    if (!event || typeof event !== "object") {
      throw new Error("Received an invalid event from the ZIP scan stream.");
    }

    if (event.type === "log" && typeof event.text === "string") {
      onLog(event.text);
    } else if (event.type === "complete") {
      completed = true;
    } else if (event.type === "error") {
      throw new Error(event.message || "The ZIP scan failed.");
    }
  };

  // Handle LF, CRLF and CR line endings without losing a split CRLF pair.
  const consumeLines = (atEnd = false) => {
    let lineEnd: number;
    while (!completed && (lineEnd = buffer.search(/[\r\n]/)) !== -1) {
      if (!atEnd && buffer[lineEnd] === "\r" && lineEnd === buffer.length - 1) break;
      const line = buffer.slice(0, lineEnd);
      const separatorLength = buffer[lineEnd] === "\r" && buffer[lineEnd + 1] === "\n" ? 2 : 1;
      buffer = buffer.slice(lineEnd + separatorLength);

      if (line === "") {
        dispatchEvent();
      } else if (line === "data" || line.startsWith("data:")) {
        dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      // Ignore SSE comments, heartbeats and other fields.
    }
  };

  try {
    while (!completed) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      consumeLines(done);
      if (done) break;
    }
    if (!completed) {
      throw new Error("The ZIP scan stream ended before a completion event was received. Please retry.");
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // A disconnected stream may already be closed or errored.
    }
    reader.releaseLock();
  }
}

export function Plagiarism() {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const zipInputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Mode Switcher: Direct Intake vs Git Repository
  const [activeTab, setActiveTab] = useState<"direct" | "git">("direct");

  // Direct Upload Intake State (global — survives navigation)
  const projectName = useScanStore((s) => s.projectName);
  const uploadedFiles = useScanStore((s) => s.uploadedFiles);
  const [isDragging, setIsDragging] = useState(false);
  const isProcessingFiles = useScanStore((s) => s.isProcessingFiles);
  const isTraversing = useScanStore((s) => s.isTraversing);
  const totalFilesToProcess = useScanStore((s) => s.totalFilesToProcess);
  const processedFilesCount = useScanStore((s) => s.processedFilesCount);
  const processingPhase = useScanStore((s) => s.processingPhase);
  
  // Bloat Elimination Stats (global — survives navigation)
  const bloatFilteredCount = useScanStore((s) => s.bloatFilteredCount);
  const inspectedTotalNodes = useScanStore((s) => s.inspectedTotalNodes);

  // Git Repository Intake State
  const [gitRepoUrl, setGitRepoUrl] = useState<string>("");
  const [gitBranch, setGitBranch] = useState<string>("main");
  const [gitAccessToken, setGitAccessToken] = useState<string>("");
  const [gitProjectTitle, setGitProjectTitle] = useState<string>("");

  // Staged Files Explorer
  const [showExplorer, setShowExplorer] = useState(false);
  const [stagedSearch, setStagedSearch] = useState("");
  const [stagedCategory, setStagedCategory] = useState<"all" | "code" | "text" | "archive">("all");

  // Scan & Terminal Execution Streamer (global — survives navigation)
  const isScanning = useScanStore((s) => s.isScanning);
  const scanLogs = useScanStore((s) => s.scanLogs);
  const [terminalAutoScroll, setTerminalAutoScroll] = useState(true);
  const [lastLogTimestamp, setLastLogTimestamp] = useState<number>(Date.now());
  const [timeSinceLastLog, setTimeSinceLastLog] = useState<number>(0);

  // Modals & History Inspection
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [historyList, setHistoryList] = useState<PlagiarismHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historySearch, setHistorySearch] = useState<string>("");

  // Auto-scroll terminal stream
  useEffect(() => {
    if (terminalAutoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [scanLogs, terminalAutoScroll]);

  useEffect(() => {
    setLastLogTimestamp(Date.now());
    setTimeSinceLastLog(0);
  }, [scanLogs]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isScanning) {
      interval = setInterval(() => {
        setTimeSinceLastLog(Date.now() - lastLogTimestamp);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isScanning, lastLogTimestamp]);

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  // Helper to process raw files and directories with intelligent bloat filtration
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
    const CHUNK_SIZE = 20;

    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      const chunk = files.slice(i, Math.min(i + CHUNK_SIZE, files.length));

      for (let j = 0; j < chunk.length; j++) {
        const file = chunk[j];
        const actualIndex = i + j;
        localInspectedCount++;
        const relativePath = customPaths?.[actualIndex] || (file as any).webkitRelativePath || file.name;
        const pathLower = relativePath.toLowerCase();

        // Extract root directory name if available
        if (relativePath.includes("/")) {
          const root = relativePath.split("/")[0];
          if (!detectedProjectName && root && !IGNORE_PATTERNS.includes(root)) {
            detectedProjectName = root;
          }
        }

        // Check bloat patterns (node_modules, .venv, etc.)
        const isIgnored = IGNORE_PATTERNS.some(p => 
          pathLower.includes(`/${p}/`) || pathLower.startsWith(`${p}/`) || pathLower.includes(`\\${p}\\`)
        );
        if (isIgnored) {
          localBloatCount++;
          continue;
        }

        const ext = file.name.split(".").pop()?.toLowerCase() || "";
        if (BINARY_EXTS.has(ext)) {
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

        // Read text content for scanning (supports up to 10MB per code/report file)
        let contentText: string | undefined = undefined;
        if ((fileType === "code" || fileType === "text") && file.size < 10 * 1024 * 1024) {
          try {
            contentText = await file.text();
          } catch (e) {
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

      // Yield to UI after each chunk
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      useScanStore.getState().setProcessingState({
        processed: i + chunk.length,
        phase: `Reading file content (${(i + chunk.length).toLocaleString()}/${files.length.toLocaleString()}) — ${elapsed}s elapsed`,
      });
      await new Promise(r => requestAnimationFrame(r));
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

  // Directory entry traversal for multi-folder drag and drop
  const traverseDirectoryEntry = async (entry: any, path = ""): Promise<{ file: File; path: string }[]> => {
    return new Promise((resolve) => {
      if (entry.isFile) {
        entry.file((file: File) => {
          resolve([{ file, path: path ? `${path}/${file.name}` : file.name }]);
        }, () => resolve([]));
      } else if (entry.isDirectory) {
        const dirReader = entry.createReader();
        const entries: any[] = [];
        const readEntries = () => {
          dirReader.readEntries(async (result: any[]) => {
            if (result.length === 0) {
              const nestedFiles: { file: File; path: string }[] = [];
              for (const childEntry of entries) {
                const childPath = path ? `${path}/${entry.name}` : entry.name;
                const childFiles = await traverseDirectoryEntry(childEntry, childPath);
                nestedFiles.push(...childFiles);
              }
              resolve(nestedFiles);
            } else {
              entries.push(...result);
              readEntries();
            }
          }, () => resolve([]));
        };
        readEntries();
      } else {
        resolve([]);
      }
    });
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
    useScanStore.getState().setProcessingState({ isTraversing: true, phase: 'Scanning directory structure...' });

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

  // Dynamic statistics for Direct Upload
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

  // Start Direct Upload Scan with Live Terminal Execution Stream
  const startDirectScan = async () => {
    if (isScanning) return;
    if (uploadedFiles.length === 0) {
      toast.error(t("no_files_staged"));
      return;
    }

    const archives = uploadedFiles.filter(f => f.type === "archive");
    if (archives.some(f => !f.name.toLowerCase().endsWith(".zip"))) {
      toast.error("Only .zip archives are supported. Remove other archive formats before scanning.");
      return;
    }
    if (archives.length > 0 && uploadedFiles.length !== 1) {
      toast.error("Scan one ZIP archive at a time, without additional staged files.");
      return;
    }

    const zipFile = archives[0];
    const activeProjectName = projectName.trim() || (uploadedFiles[0].path.includes("/") ? uploadedFiles[0].path.split("/")[0] : "Intake_Project");
    const appendLog = (text: string) => useScanStore.getState().appendLog(text);
    const onComplete = () => {
      appendLog(`[${new Date().toLocaleTimeString()}] [COMPLETED] ✅ Scan completed for ${activeProjectName}.`);
      toast.success(t("intake_progress_title") + " ✓");
    };
    const onError = (message: string) => {
      appendLog(`[${new Date().toLocaleTimeString()}] [ERROR] ❌ ${message}`);
      toast.error(message);
    };

    const controller = new AbortController();
    useScanStore.getState().setAbortController(controller);
    useScanStore.getState().startScan(activeProjectName);
    appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Staging ${uploadedFiles.length} files (${formatFileSize(totalStagedSize)})`);
    appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Checking project: ${activeProjectName}`);

    try {
      // Preserve the existing best-effort duplicate check.
      const res = await fetch(`/api/plagiarism/projects/check?names=${encodeURIComponent(activeProjectName)}`).catch(() => null);
      if (res?.ok) {
        const data = await res.json();
        if (data.exists || (data.existing_projects && data.existing_projects.length > 0)) {
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
        const response = await fetch("/api/plagiarism/upload-zip-stream", {
          method: "POST",
          headers: { Accept: "text/event-stream" },
          body: formData,
          signal: controller.signal,
        });
        await readZipScanStream(response, appendLog);
        onComplete();
      } else {
        appendLog(`[${new Date().toLocaleTimeString()}] [INTAKE] Code files: ${stagedCodeCount}, Documents: ${stagedDocCount}, Total LOC: ${stagedLoc}`);
        const payloadFiles = uploadedFiles
          .filter(f => f.content && f.type !== "other" && f.type !== "archive")
          .map(f => ({
            path: f.path,
            content: f.content || "",
            file_type: f.type,
          }));

        await plagiarismApi.uploadAndScanStream(
          activeProjectName,
          payloadFiles,
          "Direct Upload Project Scan",
          appendLog,
          onComplete,
          onError,
          controller.signal
        );
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to upload and scan the project.");
    } finally {
      useScanStore.setState({ isScanning: false });
    }
  };

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

    await plagiarismApi.scanGitRepoStream(
      payload,
      (logText) => {
        useScanStore.getState().appendLog(logText);
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
      controller.signal
    );
  };

  // Fetch Database Scan History
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

  const copyTerminalLogs = () => {
    navigator.clipboard.writeText(scanLogs.join("\n"));
    toast.success(t("logs_copied"));
  };

  const downloadTerminalLogs = () => {
    const blob = new Blob([scanLogs.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plagiarism-scan-log-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const cancelScan = () => {
    const cancel = useScanStore.getState().abortController;
    if (cancel) cancel.abort();
    useScanStore.getState().resetScan();
  };

  // History filtering
  const filteredHistory = historyList.filter(h => {
    if (!historySearch.trim()) return true;
    const q = historySearch.toLowerCase();
    return (h.project_name || "").toLowerCase().includes(q) || (h.id || "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-6 pb-12">
      {/* Hidden file inputs */}
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileSelect} 
        multiple 
        className="hidden" 
      />
      <input 
        type="file" 
        ref={zipInputRef} 
        onChange={handleZipSelect} 
        accept=".zip" 
        className="hidden" 
      />

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-3">
            <ShieldAlert className="w-7 h-7 text-accent" />
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
              className="px-3.5 py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-semibold flex items-center gap-1.5 border border-red-500/20 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              {t("clear_all")}
            </button>
          )}
          <button 
            onClick={handleOpenHistory}
            className="bg-surface/60 hover:bg-surface border border-glass-border rounded-xl px-4 py-2 flex items-center gap-2 text-sm font-semibold text-text-main transition-colors shrink-0 shadow-sm"
          >
            <History className="w-4 h-4 text-accent" />
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
              ? "border-accent text-accent"
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
              ? "border-accent text-accent"
              : "border-transparent text-text-muted hover:text-text-main"
          }`}
        >
          <Code2 className="w-4 h-4" />
          {t("tab_git_repo")}
        </button>
      </div>

      {/* TAB 1: DIRECT UPLOAD & MULTI-FOLDER DRAG & DROP INTAKE */}
      {activeTab === "direct" && (
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Pro-Tip Banner */}


          <div className="glass-card !p-6 relative overflow-hidden">
            <div 
              className={`border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-10 transition-all duration-300 cursor-pointer ${
                isDragging 
                  ? 'border-accent bg-accent/10 scale-[1.01] shadow-[0_0_30px_rgba(249,115,22,0.2)]' 
                  : (isProcessingFiles || isTraversing)
                  ? 'border-accent/50 bg-accent/5'
                  : 'border-glass-border bg-surface/20 hover:border-accent/60 hover:bg-surface/30'
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(isProcessingFiles || isTraversing) ? undefined : handleDrop}
              onClick={(isProcessingFiles || isTraversing) ? undefined : () => zipInputRef.current?.click()}
            >
              {(isProcessingFiles || isTraversing) ? (
                <div className="flex flex-col items-center w-full max-w-md animate-in fade-in zoom-in duration-300">
                  <div className="w-20 h-20 rounded-3xl bg-surface border border-glass-border flex items-center justify-center mb-4 shadow-2xl">
                    <RefreshCw className="w-10 h-10 text-accent animate-spin" />
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
                      <div className="h-2 w-full bg-background/50 rounded-full overflow-hidden border border-glass-border/30">
                        <div 
                          className="h-full bg-gradient-to-r from-accent to-primary-hover rounded-full shadow-[0_0_10px_rgba(249,115,22,0.5)] transition-all duration-300 ease-out" 
                          style={{ width: `${(processedFilesCount / totalFilesToProcess) * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div className="w-20 h-20 rounded-3xl bg-surface border border-glass-border flex items-center justify-center mb-4 shadow-2xl group">
                    <UploadCloud className={`w-10 h-10 transition-transform group-hover:scale-110 ${isDragging ? 'text-accent' : 'text-text-muted'}`} />
                  </div>
                  
                  <h2 className="text-xl font-bold text-text-main text-center">
                    {t("unified_upload_title")}
                  </h2>
                  <p className="text-xs text-text-muted mt-2 mb-6 text-center max-w-xl leading-relaxed">
                    {t("unified_upload_sub")}
                  </p>

                  {/* Quick Action Buttons inside the dropzone */}
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

            {/* Smart Bloat Elimination & Intake Progress Indicator */}
            {(uploadedFiles.length > 0 || bloatFilteredCount > 0) && (
              <div className="mt-5 pt-5 border-t border-glass-border/40 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="text-xs font-semibold text-text-muted flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      {t("intake_progress_title")}:
                    </span>

                    {bloatFilteredCount > 0 && (
                      <span className="px-2.5 py-1 rounded-full bg-text-muted/10 border border-text-muted/20 text-text-muted text-xs font-medium">
                        🛡️ {bloatFilteredCount} {t("intake_bloat_eliminated")}
                      </span>
                    )}

                    <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
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
                    <HardDrive className="w-3.5 h-3.5 text-accent" />
                    {t("staged_files_header")} ({uploadedFiles.length})
                    {showExplorer ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {/* Staged stats pills */}
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs">
                    <FileCode2 className="w-3.5 h-3.5" />
                    {stagedCodeCount} {t("code_files")}
                  </div>
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                    <FileText className="w-3.5 h-3.5" />
                    {stagedDocCount} {t("doc_files")}
                  </div>
                  {stagedArchiveCount > 0 && (
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-accent/10 border border-accent/20 text-accent-text text-xs">
                      <FileArchive className="w-3.5 h-3.5" />
                      {stagedArchiveCount} {t("archive_files")}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
                    <TerminalSquare className="w-3.5 h-3.5" />
                    {stagedLoc.toLocaleString()} {t("loc_staged_metric")}
                  </div>
                </div>
              </div>
            )}

            {/* Interactive Staged Content Explorer */}
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
                        className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "all" ? "bg-accent text-white" : "bg-surface text-text-muted hover:text-text-main"}`}
                      >
                        {t("all_files")} ({uploadedFiles.length})
                      </button>
                      <button 
                        onClick={() => setStagedCategory("code")}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "code" ? "bg-primary text-white" : "bg-surface text-text-muted hover:text-text-main"}`}
                      >
                        {t("code_files")} ({stagedCodeCount})
                      </button>
                      <button 
                        onClick={() => setStagedCategory("text")}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "text" ? "bg-amber-500 text-white" : "bg-surface text-text-muted hover:text-text-main"}`}
                      >
                        {t("doc_files")} ({stagedDocCount})
                      </button>
                      {stagedArchiveCount > 0 && (
                        <button 
                          onClick={() => setStagedCategory("archive")}
                          className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${stagedCategory === "archive" ? "bg-accent text-white" : "bg-surface text-text-muted hover:text-text-main"}`}
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

                  {/* Staged file list */}
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
                            className="text-text-muted hover:text-red-400 p-1 rounded transition-colors"
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
          </div>

          {/* PRIMARY CTA BAR FOR DIRECT INTAKE */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 glass-card !p-5">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-accent/15 rounded-xl border border-accent/30 text-accent">
                <Cpu className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-text-main">{t("codebert_title")} & {t("nlp_title")}</h3>
                <p className="text-xs text-text-muted">{t("nat_registry_active")}</p>
              </div>
            </div>

            <button 
              onClick={startDirectScan}
              disabled={isScanning || isProcessingFiles || isTraversing || uploadedFiles.length === 0}
              className="w-full sm:w-auto bg-gradient-to-r from-primary to-primary-hover hover:from-primary-hover hover:to-primary text-white font-bold text-base rounded-xl px-8 py-3.5 shadow-[0_0_25px_rgba(239,68,68,0.25)] hover:shadow-[0_0_35px_rgba(239,68,68,0.4)] transition-all flex items-center justify-center gap-2.5 transform active:scale-95 disabled:opacity-40 disabled:pointer-events-none"
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
        </motion.div>
      )}

      {/* TAB 2: GIT / GITHUB REPOSITORY INTAKE */}
      {activeTab === "git" && (
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
                  <Globe className="w-3.5 h-3.5 text-accent" />
                  {t("git_repo_url")} <span className="text-red-400">*</span>
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
                  <FileText className="w-3.5 h-3.5 text-amber-400" />
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
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
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
                <Info className="w-4 h-4 text-accent shrink-0" />
                <span>Shallow Clone depth=1 • Automated .gitignore bloat exclusion • Ephemeral secure sandbox</span>
              </span>
              <span className="font-semibold text-emerald-400">Security Gate: Active</span>
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
              className="w-full sm:w-auto bg-gradient-to-r from-primary to-primary-hover hover:from-primary-hover hover:to-primary-hover text-white font-bold text-base rounded-xl px-8 py-3.5 shadow-[0_0_25px_rgba(59,130,246,0.25)] hover:shadow-[0_0_35px_rgba(59,130,246,0.4)] transition-all flex items-center justify-center gap-2.5 transform active:scale-95 disabled:opacity-40 disabled:pointer-events-none"
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
      )}

      {/* LIVE TERMINAL EXECUTION STREAMER */}
      {(isScanning || scanLogs.length > 0) && (
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-surface/80 rounded-xl overflow-hidden"
        >
          <div className="p-3.5 px-5 bg-surface/80 border-b border-glass-border flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono font-bold text-text-muted flex items-center gap-2">
                <Terminal className="w-4 h-4 text-accent" />
                {t("live_terminal_title")}
              </span>
              {isScanning && (
                <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] font-bold text-emerald-400 animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  {t("live_stream_active")}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {isScanning && (
                <button 
                  onClick={cancelScan}
                  className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 transition-colors"
                  title="Cancel Scan"
                >
                  Cancel Scan
                </button>
              )}
              <button 
                onClick={() => setTerminalAutoScroll(!terminalAutoScroll)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-colors ${terminalAutoScroll ? 'bg-accent/20 text-accent border border-accent/30' : 'bg-surface text-text-muted'}`}
              >
                Auto-Scroll: {terminalAutoScroll ? "ON" : "OFF"}
              </button>
              <button 
                onClick={copyTerminalLogs}
                className="p-1.5 rounded-lg bg-surface hover:bg-surface-hover text-text-muted hover:text-text-main transition-colors"
                title={t("copy_logs")}
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
              <button 
                onClick={downloadTerminalLogs}
                className="p-1.5 rounded-lg bg-surface hover:bg-surface-hover text-text-muted hover:text-text-main transition-colors"
                title={t("download_logs")}
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div dir="ltr" role="log" aria-label={t("live_terminal_title")} aria-live="polite" aria-relevant="additions text" className="p-4 bg-surface text-text-main font-mono text-xs max-h-64 overflow-y-auto space-y-1 leading-relaxed selection:bg-accent/30 text-left">
            {scanLogs.map((log, idx) => {
              const isAst = log.includes("[AST]");
              const isNlp = log.includes("[NLP]");
              const isMinhash = log.includes("[MINHASH]") || log.includes("[LSH]");
              const isGit = log.includes("[GIT]") || log.includes("🐙");
              const isError = log.includes("[ERROR]") || log.includes("❌");
              const isCompleted = log.includes("[COMPLETED]") || log.includes("[DONE]") || log.includes("✅");

              return (
                <div 
                  key={idx} 
                  className={`flex items-start gap-2 ${
                    isError 
                      ? 'text-red-400' 
                      : isCompleted 
                      ? 'text-emerald-400 font-bold' 
                      : isAst 
                      ? 'text-warning' 
                      : isNlp 
                      ? 'text-danger' 
                      : isGit 
                      ? 'text-primary'
                      : isMinhash 
                      ? 'text-primary' 
                      : 'text-text-muted'
                  }`}
                >
                  <span className="text-text-muted select-none">&gt;</span>
                  <span className="whitespace-pre-wrap break-words min-w-0">{log}</span>
                </div>
              );
            })}
            {isScanning && timeSinceLastLog > 2000 && (
              <div className="flex items-start gap-2">
                <span className="text-text-muted select-none">&gt;</span>
                <span className="text-accent font-mono">Waiting for the next backend update… {Math.floor(timeSinceLastLog / 1000)}s since the last message.</span>
              </div>
            )}
            <div ref={terminalEndRef} />
          </div>
        </motion.div>
      )}

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
                    <History className="w-5 h-5 text-accent" />
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
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-accent" />
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
                      <span className={`text-sm font-bold ${h.overall_similarity >= 65 ? 'text-red-400' : h.overall_similarity >= 25 ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {h.overall_similarity}%
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                        h.verdict === 'SAFE' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'
                      }`}>
                        {h.verdict}
                      </span>
                      <button
                        onClick={() => {
                          setIsHistoryOpen(false);
                          toast.success(`${t("inspect_report")}: ${h.project_name || h.id}`);
                        }}
                        className="px-2.5 py-1.5 rounded-lg bg-accent text-white font-medium text-xs flex items-center gap-1 shadow-sm transition-all hover:scale-105"
                        title={t("inspect_report")}
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                      <button 
                        onClick={() => handleDeleteHistoryReport(h.id)}
                        className="p-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 text-xs transition-colors"
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
