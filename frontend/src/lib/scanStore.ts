import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { PlagiarismScanResult } from './api';

/** Cap on the persisted log tail — keeps localStorage well inside its ~5 MB quota. */
const MAX_PERSISTED_LOGS = 400;

/** A "running" scan older than this is dead, not resumable (server restart, sleep...). */
const STALE_SCAN_MS = 2 * 60 * 60 * 1000;

export interface UploadedFileInfo {
  id: string;
  path: string;
  name: string;
  size: number;
  type: "code" | "text" | "archive" | "other";
  content?: string;
  file: File;
}

interface ScanStore {
  // --- Group A: Pre-scan / Upload state (survives navigation) ---
  uploadedFiles: UploadedFileInfo[];
  projectName: string;
  isProcessingFiles: boolean;
  isTraversing: boolean;
  totalFilesToProcess: number;
  processedFilesCount: number;
  processingPhase: string;
  bloatFilteredCount: number;
  inspectedTotalNodes: number;

  // --- Group B: Scan execution state (survives navigation) ---
  isScanning: boolean;
  scanLogs: string[];
  scanResult: PlagiarismScanResult | null;
  scanError: string | null;

  // --- Group C: Stream re-attach state (survives reloads & navigation) ---
  /** Project the in-flight scan belongs to; keys the backend stream session. */
  activeProjectId: string | null;
  /** Per-scan capability token that authorises an EventSource re-attach. */
  streamToken: string | null;
  /** Epoch ms of scan start — used to discard hopelessly stale scans. */
  scanStartedAt: number | null;
  /** True while a re-attached EventSource is catching up / following the stream. */
  isReconnecting: boolean;
  /** Server-emitted log lines we hold — the resume cursor used when re-attaching. */
  streamLogCount: number;

  // --- Actions ---
  setUploadedFiles: (files: UploadedFileInfo[] | ((prev: UploadedFileInfo[]) => UploadedFileInfo[])) => void;
  setProjectName: (name: string) => void;
  setProcessingState: (state: { isProcessing?: boolean; isTraversing?: boolean; total?: number; processed?: number; phase?: string }) => void;
  setBloatStats: (filtered: number, totalNodes: number) => void;
  
  appendLog: (text: string) => void;
  /** Append a line that came FROM the backend stream, advancing the resume cursor. */
  noteServerLog: (text: string) => void;
  startScan: (projectName: string) => void;
  completeScan: (result: PlagiarismScanResult) => void;
  failScan: (error: string) => void;
  resetScan: () => void;
  resetAll: () => void;

  // AbortController (to cancel on demand, NOT on unmount)
  abortController: AbortController | null;
  setAbortController: (c: AbortController | null) => void;

  // Group C actions
  /** Store the reconnect capability delivered as the first frame of a scan stream. */
  setStreamSession: (projectId: string, token: string) => void;
  /** Mark the store as re-attaching to an already-running scan for `projectId`. */
  reconnectScan: (projectId: string) => void;
  /** The live stream is gone (server restart / TTL): stop the spinner, keep the logs. */
  markScanInterrupted: (message: string) => void;
  /** Forget the capability once a stream has terminally finished. */
  endStreamSession: () => void;
}

export const useScanStore = create<ScanStore>()(persist((set) => ({
  // Group A defaults
  uploadedFiles: [],
  projectName: '',
  isProcessingFiles: false,
  isTraversing: false,
  totalFilesToProcess: 0,
  processedFilesCount: 0,
  processingPhase: '',
  bloatFilteredCount: 0,
  inspectedTotalNodes: 0,

  // Group B defaults
  isScanning: false,
  scanLogs: [],
  scanResult: null,
  scanError: null,
  abortController: null,

  // Group C defaults
  activeProjectId: null,
  streamToken: null,
  scanStartedAt: null,
  isReconnecting: false,
  streamLogCount: 0,

  // Group A actions
  setUploadedFiles: (files) => set((s) => ({
    uploadedFiles: typeof files === 'function' ? files(s.uploadedFiles) : files
  })),
  setProjectName: (name) => set({ projectName: name }),
  setProcessingState: (state) => set((s) => ({
    isProcessingFiles: state.isProcessing ?? s.isProcessingFiles,
    isTraversing: state.isTraversing ?? s.isTraversing,
    totalFilesToProcess: state.total ?? s.totalFilesToProcess,
    processedFilesCount: state.processed ?? s.processedFilesCount,
    processingPhase: state.phase ?? s.processingPhase,
  })),
  setBloatStats: (filtered, totalNodes) => set({ bloatFilteredCount: filtered, inspectedTotalNodes: totalNodes }),

  // Group B actions
  appendLog: (text) => set((s) => ({ scanLogs: [...s.scanLogs, text] })),
  // Server-originated lines advance the resume cursor, so a re-attach can ask the
  // backend to replay only what we missed (`?after=streamLogCount`) instead of
  // re-appending the whole terminal on every navigate-back.
  noteServerLog: (text) => set((s) => ({
    scanLogs: [...s.scanLogs, text],
    streamLogCount: s.streamLogCount + 1,
  })),
  startScan: (name) => set({
    isScanning: true, scanLogs: [], scanResult: null, scanError: null, projectName: name,
    // A brand-new scan invalidates any previous reconnect capability.
    activeProjectId: name, streamToken: null, scanStartedAt: Date.now(), isReconnecting: false,
    streamLogCount: 0,
  }),
  completeScan: (result) => set({
    isScanning: false, isReconnecting: false, scanResult: result,
    // Stream finished: drop the capability so we never re-attach to a dead stream.
    streamToken: null,
  }),
  failScan: (error) => set({ isScanning: false, isReconnecting: false, scanError: error, streamToken: null }),
  resetScan: () => set({
    isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null,
    activeProjectId: null, streamToken: null, scanStartedAt: null, isReconnecting: false,
    streamLogCount: 0,
  }),
  resetAll: () => set({
    uploadedFiles: [], projectName: '', isProcessingFiles: false, isTraversing: false,
    totalFilesToProcess: 0, processedFilesCount: 0, processingPhase: '',
    bloatFilteredCount: 0, inspectedTotalNodes: 0,
    isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null,
    activeProjectId: null, streamToken: null, scanStartedAt: null, isReconnecting: false,
    streamLogCount: 0,
  }),
  setAbortController: (c) => set({ abortController: c }),

  // Group C actions
  setStreamSession: (projectId, token) => set({
    activeProjectId: projectId,
    streamToken: token,
    scanStartedAt: Date.now(),
  }),

  reconnectScan: (projectId) => set((s) => ({
    isScanning: true,
    isReconnecting: true,
    activeProjectId: projectId,
    scanError: null,
    projectName: s.projectName || projectId,
    // Keep the logs we already hold: the server replays only what *it* emitted, so
    // wiping them would lose the client-side lines written before navigation.
    scanLogs: [
      ...s.scanLogs,
      `[${new Date().toLocaleTimeString()}] [RESUME] Re-attaching to the live scan stream for '${projectId}'...`,
    ],
  })),

  markScanInterrupted: (message) => set((s) => ({
    isScanning: false,
    isReconnecting: false,
    scanError: message,
    streamToken: null,
    scanLogs: [
      ...s.scanLogs,
      `[${new Date().toLocaleTimeString()}] [INTERRUPTED] ${message}`,
    ],
  })),

  endStreamSession: () => set({
    isReconnecting: false, streamToken: null, activeProjectId: null, scanStartedAt: null,
  }),
}), {
  name: 'plagiarism-scan-storage',
  version: 1,
  // Only serialisable state is persisted. `abortController` (an AbortController) and
  // each staged file's `File` handle / raw content are deliberately dropped: none of
  // them survive `JSON.stringify`, and the absence of `abortController` after a reload
  // is exactly how the intake page detects "no local reader owns this stream, so
  // re-attach with an EventSource".
  partialize: (s) => ({
    // Group A — metadata only; a reloaded staged list is descriptive, so files must
    // be re-staged to start a *new* scan (resuming a live one needs neither).
    uploadedFiles: s.uploadedFiles.map(({ file, content, ...meta }) => meta as UploadedFileInfo),
    projectName: s.projectName,
    isProcessingFiles: s.isProcessingFiles,
    isTraversing: s.isTraversing,
    totalFilesToProcess: s.totalFilesToProcess,
    processedFilesCount: s.processedFilesCount,
    processingPhase: s.processingPhase,
    bloatFilteredCount: s.bloatFilteredCount,
    inspectedTotalNodes: s.inspectedTotalNodes,
    // Group B
    isScanning: s.isScanning,
    scanLogs: s.scanLogs.slice(-MAX_PERSISTED_LOGS),
    scanResult: s.scanResult,
    scanError: s.scanError,
    // Group C — the reconnect capability
    activeProjectId: s.activeProjectId,
    streamToken: s.streamToken,
    scanStartedAt: s.scanStartedAt,
    streamLogCount: s.streamLogCount,
  }),
  // Runs once, synchronously, as the persisted state is read back on page load.
  // The hydrated draft is mutated directly because `useScanStore` is not assigned
  // yet while `create(...)` is still executing.
  onRehydrateStorage: () => (state) => {
    if (!state) return;

    // An EventSource cannot survive a page load, so nothing is "reconnecting" yet —
    // the intake page's mount effect decides whether to re-attach.
    state.isReconnecting = false;
    // A rehydrated AbortController would be a lie: no local request is in flight.
    state.abortController = null;
    // Client-side traversal/reading cannot survive a reload either; leaving these
    // set would pin a progress bar that will never advance.
    state.isProcessingFiles = false;
    state.isTraversing = false;

    const startedAt = state.scanStartedAt;
    const isStale = startedAt !== null && Date.now() - startedAt > STALE_SCAN_MS;
    const isResumable = Boolean(state.activeProjectId && state.streamToken) && !isStale;

    if (state.isScanning && !isResumable) {
      // Never leave the terminal spinning on a scan nobody can resume.
      state.isScanning = false;
      state.streamToken = null;
      state.scanError =
        'The previous scan could not be resumed (its live stream expired). Check Scan History for the final report.';
    }
  },
}));
