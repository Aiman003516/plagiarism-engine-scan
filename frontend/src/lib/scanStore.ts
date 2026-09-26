import { create } from 'zustand';
import type { PlagiarismScanResult } from './api';

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

  // --- Actions ---
  setUploadedFiles: (files: UploadedFileInfo[] | ((prev: UploadedFileInfo[]) => UploadedFileInfo[])) => void;
  setProjectName: (name: string) => void;
  setProcessingState: (state: { isProcessing?: boolean; isTraversing?: boolean; total?: number; processed?: number; phase?: string }) => void;
  setBloatStats: (filtered: number, totalNodes: number) => void;
  
  appendLog: (text: string) => void;
  startScan: (projectName: string) => void;
  completeScan: (result: PlagiarismScanResult) => void;
  failScan: (error: string) => void;
  resetScan: () => void;
  resetAll: () => void;

  // AbortController (to cancel on demand, NOT on unmount)
  abortController: AbortController | null;
  setAbortController: (c: AbortController | null) => void;
}

export const useScanStore = create<ScanStore>((set) => ({
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
  startScan: (name) => set({ isScanning: true, scanLogs: [], scanResult: null, scanError: null, projectName: name }),
  completeScan: (result) => set({ isScanning: false, scanResult: result }),
  failScan: (error) => set({ isScanning: false, scanError: error }),
  resetScan: () => set({ isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null }),
  resetAll: () => set({
    uploadedFiles: [], projectName: '', isProcessingFiles: false, isTraversing: false,
    totalFilesToProcess: 0, processedFilesCount: 0, processingPhase: '',
    bloatFilteredCount: 0, inspectedTotalNodes: 0,
    isScanning: false, scanLogs: [], scanResult: null, scanError: null, abortController: null,
  }),
  setAbortController: (c) => set({ abortController: c }),
}));
