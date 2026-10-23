import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Database, Search, RefreshCw, AlertTriangle, ShieldCheck, GitCompare, Eye, X } from 'lucide-react';
import { toast } from 'react-hot-toast';
import {
  plagiarismApi,
  DeepScanResult,
  ProjectComparisonResult,
  ProjectComparisonMatch,
  PlagiarismComparison,
  PlagiarismScanResult,
  DirectCompareFilesResult,
  ProjectFile,
} from '../lib/api';
import { UploadCloud, FileText, CheckCircle2, Scale, History, FolderOpen } from 'lucide-react';
import { ScanHistoryModal } from './plagiarism/ScanHistoryModal';
import DiffViewer from '../components/DiffViewer';
import { SummaryCards } from './plagiarism/SummaryCards';
import { ComparisonsTable } from './plagiarism/ComparisonsTable';
import { DeepScanPanel } from './plagiarism/DeepScanPanel';
import { ScanProgress } from './plagiarism/ScanProgress';
import { useScanStore } from '../lib/scanStore';
import { handleStreamSession, useScanStreamReconnection } from './plagiarism/hooks/useScanStream';
import { useProjectsCache } from '../lib/useProjectsCache';

export function PlagiarismAnalysis() {
  const location = useLocation();
  // Re-attach scan stream if a scanner scan is in flight
  useScanStreamReconnection("scanner");

  const {
    projects: savedProjects,
    loading: loadingProjects,
    error: projectsError,
    refresh: refreshProjects,
  } = useProjectsCache();

  // Persistent scanStore: scan execution & live streaming survive navigation and reloads
  const scanSource = useScanStore((s) => s.scanSource);
  const isScanning = useScanStore((s) => s.isScanning && s.scanSource === "scanner");
  const scanResult = useScanStore((s) => s.scanResult);
  const scanError = useScanStore((s) => s.scanSource === "scanner" ? s.scanError : null);
  const activeProjectId = useScanStore((s) => s.activeProjectId);
  const scanDuration = useScanStore((s) => s.scanDuration) ?? 0;

  // Deep scan store integration (concurrent scans + persistent cache)
  const activeDeepScans = useScanStore((s) => s.activeDeepScans) || [];
  const deepScanResultsCache = useScanStore((s) => s.deepScanResultsCache) || {};

  // Scan History Modal state
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  // Direct Two-File / Document Pair Comparison state (Upload or Database)
  const [modeA, setModeA] = useState<'upload' | 'database'>('upload');
  const [modeB, setModeB] = useState<'upload' | 'database'>('upload');
  const [fileA, setFileA] = useState<File | null>(null);
  const [fileB, setFileB] = useState<File | null>(null);
  const [dbProjectA, setDbProjectA] = useState<string>('');
  const [dbFileA, setDbFileA] = useState<string>('');
  const [projectAFiles, setProjectAFiles] = useState<ProjectFile[]>([]);
  const [loadingFilesA, setLoadingFilesA] = useState(false);

  const [dbProjectB, setDbProjectB] = useState<string>('');
  const [dbFileB, setDbFileB] = useState<string>('');
  const [projectBFiles, setProjectBFiles] = useState<ProjectFile[]>([]);
  const [loadingFilesB, setLoadingFilesB] = useState(false);

  const [isComparingFiles, setIsComparingFiles] = useState(false);
  const [directResult, setDirectResult] = useState<DirectCompareFilesResult | null>(null);
  const [directError, setDirectError] = useState<string | null>(null);
  const [showDirectDiffModal, setShowDirectDiffModal] = useState(false);
  const [isDraggingA, setIsDraggingA] = useState(false);
  const [isDraggingB, setIsDraggingB] = useState(false);

  const [selectedProject, setSelectedProject] = useState<string>(() => activeProjectId || '');
  const [deepScanResult, setDeepScanResult] = useState<DeepScanResult | null>(null);

  // Keep selectedProject aligned if an active scan is running
  useEffect(() => {
    if (activeProjectId && !selectedProject) {
      setSelectedProject(activeProjectId);
    }
  }, [activeProjectId]);

  // Direct Project Comparison state
  const [projectA, setProjectA] = useState<string>('');
  const [projectB, setProjectB] = useState<string>('');
  const [isComparing, setIsComparing] = useState(false);
  const [comparisonResult, setComparisonResult] = useState<ProjectComparisonResult | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  // File pair currently open in the visual Diff Viewer modal
  const [diffTarget, setDiffTarget] = useState<ProjectComparisonMatch | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const projParam = params.get('project');
    if (projParam) {
      setSelectedProject(projParam);
      const start = Date.now();
      plagiarismApi.getHistoryDetail(projParam)
        .then((res) => {
          const dur = (Date.now() - start) / 1000;
          useScanStore.getState().completeScan(res as PlagiarismScanResult, dur);
        })
        .catch((e) => {
          useScanStore.getState().failScan(e.message || "Failed to load report");
          toast.error("Failed to load report");
        });
    }
  }, [location.search]);

  // Run a deep AI semantic scan on a matched file pair (concurrent + cached).
  const runDeepScan = async (cmp: PlagiarismComparison) => {
    if (!scanResult) return;
    const file2 = cmp.file2 || cmp.matched_file || '';
    const key = `${cmp.file1}::${file2}`;

    if (deepScanResultsCache[key]) {
      setDeepScanResult(deepScanResultsCache[key]);
      return;
    }

    useScanStore.getState().addActiveDeepScan(key);
    try {
      const res = await plagiarismApi.deepScan({
        project_id: scanResult.project_name || scanResult.target || '',
        file1_path: cmp.file1 || '',
        other_project_id: cmp.project,
        file2_path: file2,
      });
      useScanStore.getState().cacheDeepScanResult(key, res);
      setDeepScanResult(res);
      toast.success(`Deep scan complete for ${file2}`);
    } catch (e: any) {
      toast.error(e?.message || 'Deep scan failed');
    } finally {
      useScanStore.getState().removeActiveDeepScan(key);
    }
  };

  // Load files when DB project changes
  const handleSelectDbProjectA = async (projId: string) => {
    setDbProjectA(projId);
    setDbFileA('');
    if (!projId) {
      setProjectAFiles([]);
      return;
    }
    setLoadingFilesA(true);
    try {
      const res = await plagiarismApi.getProjectFiles(projId);
      setProjectAFiles(res.files || []);
    } catch {
      toast.error('Failed to load files for Project A');
    } finally {
      setLoadingFilesA(false);
    }
  };

  const handleSelectDbProjectB = async (projId: string) => {
    setDbProjectB(projId);
    setDbFileB('');
    if (!projId) {
      setProjectBFiles([]);
      return;
    }
    setLoadingFilesB(true);
    try {
      const res = await plagiarismApi.getProjectFiles(projId);
      setProjectBFiles(res.files || []);
    } catch {
      toast.error('Failed to load files for Project B');
    } finally {
      setLoadingFilesB(false);
    }
  };

  // Direct pairwise comparison between two files/documents (upload or db)
  const runDirectFileComparison = async () => {
    const hasA = modeA === 'upload' ? Boolean(fileA) : Boolean(dbProjectA && dbFileA);
    const hasB = modeB === 'upload' ? Boolean(fileB) : Boolean(dbProjectB && dbFileB);
    if (!hasA || !hasB) return;

    setIsComparingFiles(true);
    setDirectResult(null);
    setDirectError(null);
    try {
      const res = await plagiarismApi.compareDirectFiles(
        modeA === 'upload' ? fileA : null,
        modeB === 'upload' ? fileB : null,
        modeA === 'database' ? { projectId: dbProjectA, filePath: dbFileA } : null,
        modeB === 'database' ? { projectId: dbProjectB, filePath: dbFileB } : null
      );
      setDirectResult(res);
      toast.success(`Pairwise comparison complete: ${res.similarity}% similarity`);
    } catch (e: any) {
      setDirectError(e?.message || 'File comparison failed');
      toast.error(e?.message || 'File comparison failed');
    } finally {
      setIsComparingFiles(false);
    }
  };

  // Direct head-to-head comparison of two saved projects.
  const runComparison = async () => {
    if (!projectA || !projectB || projectA === projectB) return;
    setIsComparing(true);
    setComparisonResult(null);
    setComparisonError(null);
    try {
      const res = await plagiarismApi.compareProjects({ project_a: projectA, project_b: projectB });
      setComparisonResult(res);
      toast.success(`Comparison complete: ${res.comparisons?.length || 0} matching file pairs`);
    } catch (e: any) {
      setComparisonError(e?.message || 'Comparison failed');
      toast.error(e?.message || 'Comparison failed');
    } finally {
      setIsComparing(false);
    }
  };

  const runScan = async () => {
    if (!selectedProject) return;

    useScanStore.getState().startScan(selectedProject, "scanner");
    const controller = new AbortController();
    useScanStore.getState().setAbortController(controller);
    const t0 = Date.now();

    try {
      await plagiarismApi.scanSavedProjectStream(
        selectedProject,
        'Saved Project Scan',
        (logText) => useScanStore.getState().noteServerLog(logText),
        (result) => {
          const duration = ((Date.now() - t0) / 1000);
          useScanStore.getState().completeScan(result, duration);
          toast.success(`Analysis complete in ${duration.toFixed(1)}s`);
        },
        (errorText) => {
          useScanStore.getState().failScan(errorText);
          toast.error(errorText);
        },
        controller.signal,
        handleStreamSession
      );
    } catch (e: any) {
      useScanStore.getState().failScan(e?.message || 'Scan failed');
      toast.error(e?.message || 'Scan failed');
    }
  };

  const comparisons = scanResult?.comparisons || [];

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header with History Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-main flex items-center gap-2.5">
            <Database className="w-7 h-7 text-primary" />
            Plagiarism Scanner & Analysis
          </h1>
          <p className="text-text-muted text-sm mt-0.5">
            Run system-wide scans, inspect direct pairwise file comparisons, or review past audit logs.
          </p>
        </div>
        <button
          onClick={() => setIsHistoryOpen(true)}
          className="bg-surface hover:bg-surface-hover border border-border rounded-xl px-4 py-2.5 flex items-center gap-2 text-xs font-semibold text-text-main transition-colors shrink-0 shadow-sm self-start sm:self-auto"
        >
          <History className="w-4 h-4 text-primary" />
          Scan History & Audit Logs
        </button>
      </div>

      {/* Scanner Card */}
      <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-8 flex flex-col items-center shadow-sm">
        <Database className="w-16 h-16 text-primary mb-4" />
        <h2 className="text-2xl font-bold mb-2">System-Wide Plagiarism Scanner</h2>
        <p className="text-text-muted text-center max-w-lg mb-8">
          Select a project that has already been indexed into the database to instantly run a system-wide plagiarism scan.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 w-full max-w-md">
          <div className="flex-1 flex flex-col">
            <select 
              className="w-full bg-background border border-border rounded-lg px-4 py-3 focus:ring-2 focus:ring-primary/20 outline-none text-text-main"
              value={selectedProject}
              onChange={(e) => {
                setSelectedProject(e.target.value);
                if (!isScanning) {
                  useScanStore.getState().resetScan();
                }
              }}
            >
              <option value="">
                {loadingProjects && savedProjects.length === 0
                  ? "Loading saved projects..."
                  : "Select a saved project..."}
              </option>
              {selectedProject && !savedProjects.some((p: any) => p.id === selectedProject) && (
                <option key={selectedProject} value={selectedProject}>
                  {selectedProject}
                </option>
              )}
              {savedProjects.map((p: any) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            {projectsError && savedProjects.length === 0 && (
              <button
                type="button"
                onClick={() => refreshProjects()}
                className="text-xs text-red-500 hover:underline flex items-center gap-1 mt-1.5 px-1"
              >
                <RefreshCw className="w-3 h-3" /> Failed to load projects. Click to retry.
              </button>
            )}
          </div>
          {isScanning ? (
            <div className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 font-medium">
              <RefreshCw className="w-5 h-5 animate-spin" />
              <span className="text-sm">Scanning...</span>
            </div>
          ) : (
            <button 
              onClick={runScan}
              disabled={!selectedProject}
              className="bg-accent hover:bg-accent-hover text-accent-text px-8 py-3 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 whitespace-nowrap"
            >
              <Search className="w-5 h-5" />
              Run Deep Scan
            </button>
          )}
        </div>
      </div>

      {/* Real-time Streaming Terminal */}
      <ScanProgress scope="scanner" />

      {/* Direct File & Document Pair Review (Pair-to-Pair Comparison) */}
      <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-2">
          <Scale className="w-6 h-6 text-primary" />
          <h2 className="text-xl font-bold text-text-main">Direct Document & File Pair Comparison</h2>
        </div>
        <p className="text-text-muted text-sm mb-6">
          Upload any two files (PDF, Word DOCX, source code, or plain text) for an instant pairwise deep similarity check with score breakdown and side-by-side diff.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* File A Box */}
          <div className="rounded-xl p-4 border border-border dark:border-slate-700 bg-surface/30 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-text-main">Document / File A</span>
              <div className="flex rounded-lg bg-surface border border-border p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => { setModeA('upload'); setDbProjectA(''); setDbFileA(''); }}
                  className={`px-2.5 py-1 rounded-md font-medium text-xs transition-all ${modeA === 'upload' ? 'bg-primary text-primary-text shadow-sm' : 'text-text-muted hover:text-text-main'}`}
                >
                  Upload
                </button>
                <button
                  type="button"
                  onClick={() => { setModeA('database'); setFileA(null); }}
                  className={`px-2.5 py-1 rounded-md font-medium text-xs transition-all ${modeA === 'database' ? 'bg-primary text-primary-text shadow-sm' : 'text-text-muted hover:text-text-main'}`}
                >
                  Database
                </button>
              </div>
            </div>

            {modeA === 'upload' ? (
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDraggingA(true); }}
                onDragLeave={(e) => { e.preventDefault(); setIsDraggingA(false); }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDraggingA(false);
                  const dropped = e.dataTransfer.files?.[0];
                  if (dropped) {
                    setFileA(dropped);
                    setDirectResult(null);
                    setDirectError(null);
                  }
                }}
                className={`border-2 border-dashed rounded-xl p-4 flex-1 flex flex-col items-center justify-center text-center transition-all min-h-[140px] ${
                  isDraggingA
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/30 scale-[1.01]'
                    : 'border-border dark:border-slate-700 hover:border-primary/50 bg-surface/20'
                }`}
              >
                <input
                  type="file"
                  id="direct-file-a"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      setFileA(e.target.files[0]);
                      setDirectResult(null);
                      setDirectError(null);
                    }
                  }}
                />
                {fileA ? (
                  <div className="flex flex-col items-center gap-1.5">
                    <FileText className="w-7 h-7 text-primary" />
                    <span className="font-semibold text-text-main text-xs max-w-[220px] truncate" title={fileA.name}>{fileA.name}</span>
                    <span className="text-[11px] text-text-muted">{(fileA.size / 1024).toFixed(1)} KB</span>
                    <button
                      type="button"
                      onClick={() => { setFileA(null); setDirectResult(null); }}
                      className="text-xs text-red-500 hover:underline mt-1"
                    >
                      Remove File A
                    </button>
                  </div>
                ) : (
                  <label htmlFor="direct-file-a" className="cursor-pointer flex flex-col items-center gap-1.5">
                    <UploadCloud className="w-7 h-7 text-text-muted" />
                    <span className="text-xs font-semibold text-text-main">Choose or drop File A</span>
                    <span className="text-[11px] text-text-muted">PDF, DOCX, Code, or Text</span>
                  </label>
                )}
              </div>
            ) : (
              <div className="space-y-3 flex-1 flex flex-col justify-center min-h-[140px]">
                <div>
                  <label className="block text-[11px] text-text-muted mb-1">Select Project</label>
                  <select
                    value={dbProjectA}
                    onChange={(e) => handleSelectDbProjectA(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-text-main outline-none focus:ring-1 focus:ring-primary/30"
                  >
                    <option value="">Choose a database project...</option>
                    {savedProjects.map((p) => (
                      <option key={`pa-${p.id}`} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-text-muted mb-1">Select File in Project</label>
                  <select
                    disabled={!dbProjectA || loadingFilesA}
                    value={dbFileA}
                    onChange={(e) => { setDbFileA(e.target.value); setDirectResult(null); }}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-text-main outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
                  >
                    <option value="">
                      {loadingFilesA ? 'Loading project files...' : !dbProjectA ? 'Select project first' : 'Choose a file...'}
                    </option>
                    {projectAFiles.map((f, i) => (
                      <option key={`fa-${i}`} value={f.relative_path}>{f.relative_path}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* File B Box */}
          <div className="rounded-xl p-4 border border-border dark:border-slate-700 bg-surface/30 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-text-main">Document / File B</span>
              <div className="flex rounded-lg bg-surface border border-border p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => { setModeB('upload'); setDbProjectB(''); setDbFileB(''); }}
                  className={`px-2.5 py-1 rounded-md font-medium text-xs transition-all ${modeB === 'upload' ? 'bg-primary text-primary-text shadow-sm' : 'text-text-muted hover:text-text-main'}`}
                >
                  Upload
                </button>
                <button
                  type="button"
                  onClick={() => { setModeB('database'); setFileB(null); }}
                  className={`px-2.5 py-1 rounded-md font-medium text-xs transition-all ${modeB === 'database' ? 'bg-primary text-primary-text shadow-sm' : 'text-text-muted hover:text-text-main'}`}
                >
                  Database
                </button>
              </div>
            </div>

            {modeB === 'upload' ? (
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDraggingB(true); }}
                onDragLeave={(e) => { e.preventDefault(); setIsDraggingB(false); }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDraggingB(false);
                  const dropped = e.dataTransfer.files?.[0];
                  if (dropped) {
                    setFileB(dropped);
                    setDirectResult(null);
                    setDirectError(null);
                  }
                }}
                className={`border-2 border-dashed rounded-xl p-4 flex-1 flex flex-col items-center justify-center text-center transition-all min-h-[140px] ${
                  isDraggingB
                    ? 'border-emerald-500 bg-emerald-500/10 ring-2 ring-emerald-500/30 scale-[1.01]'
                    : 'border-border dark:border-slate-700 hover:border-emerald-500/50 bg-surface/20'
                }`}
              >
                <input
                  type="file"
                  id="direct-file-b"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      setFileB(e.target.files[0]);
                      setDirectResult(null);
                      setDirectError(null);
                    }
                  }}
                />
                {fileB ? (
                  <div className="flex flex-col items-center gap-1.5">
                    <FileText className="w-7 h-7 text-emerald-500" />
                    <span className="font-semibold text-text-main text-xs max-w-[220px] truncate" title={fileB.name}>{fileB.name}</span>
                    <span className="text-[11px] text-text-muted">{(fileB.size / 1024).toFixed(1)} KB</span>
                    <button
                      type="button"
                      onClick={() => { setFileB(null); setDirectResult(null); }}
                      className="text-xs text-red-500 hover:underline mt-1"
                    >
                      Remove File B
                    </button>
                  </div>
                ) : (
                  <label htmlFor="direct-file-b" className="cursor-pointer flex flex-col items-center gap-1.5">
                    <UploadCloud className="w-7 h-7 text-text-muted" />
                    <span className="text-xs font-semibold text-text-main">Choose or drop File B</span>
                    <span className="text-[11px] text-text-muted">PDF, DOCX, Code, or Text</span>
                  </label>
                )}
              </div>
            ) : (
              <div className="space-y-3 flex-1 flex flex-col justify-center min-h-[140px]">
                <div>
                  <label className="block text-[11px] text-text-muted mb-1">Select Project</label>
                  <select
                    value={dbProjectB}
                    onChange={(e) => handleSelectDbProjectB(e.target.value)}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-text-main outline-none focus:ring-1 focus:ring-primary/30"
                  >
                    <option value="">Choose a database project...</option>
                    {savedProjects.map((p) => (
                      <option key={`pb-${p.id}`} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-text-muted mb-1">Select File in Project</label>
                  <select
                    disabled={!dbProjectB || loadingFilesB}
                    value={dbFileB}
                    onChange={(e) => { setDbFileB(e.target.value); setDirectResult(null); }}
                    className="w-full bg-background border border-border rounded-lg px-3 py-2 text-xs text-text-main outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
                  >
                    <option value="">
                      {loadingFilesB ? 'Loading project files...' : !dbProjectB ? 'Select project first' : 'Choose a file...'}
                    </option>
                    {projectBFiles.map((f, i) => (
                      <option key={`fb-${i}`} value={f.relative_path}>{f.relative_path}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end">
          <button
            disabled={
              isComparingFiles ||
              (modeA === 'upload' ? !fileA : !dbProjectA || !dbFileA) ||
              (modeB === 'upload' ? !fileB : !dbProjectB || !dbFileB)
            }
            onClick={runDirectFileComparison}
            className="bg-primary hover:bg-primary-hover text-primary-text px-6 py-2.5 rounded-lg font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 text-xs shadow-sm"
          >
            {isComparingFiles ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Scale className="w-4 h-4" />}
            {isComparingFiles ? 'Comparing Files...' : 'Compare Two Files'}
          </button>
        </div>

        {directError && (
          <div className="mt-4 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-600 dark:text-red-400 text-sm">
            {directError}
          </div>
        )}

        {directResult && (
          <div className="mt-6 p-5 rounded-xl border border-border/50 dark:border-slate-700 bg-surface/40">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
              <div>
                <div className="text-xs text-text-muted mb-1">Pairwise Similarity Score</div>
                <div className="flex items-center gap-3">
                  <span className="text-3xl font-extrabold text-text-main">{directResult.similarity}%</span>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                    directResult.verdict === 'CRITICAL' ? 'bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/30' :
                    directResult.verdict === 'HIGH' ? 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/30' :
                    directResult.verdict === 'LOW' ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30' :
                    'bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/30'
                  }`}>
                    {directResult.verdict}
                  </span>
                </div>
              </div>

              <button
                onClick={() => setShowDirectDiffModal(true)}
                className="bg-accent hover:bg-accent-hover text-accent-text px-4 py-2 rounded-lg font-medium text-xs transition-colors flex items-center gap-1.5 shadow-sm"
              >
                <Eye className="w-4 h-4" />
                View Side-by-Side Diff ({directResult.matched_lines} identical lines)
              </button>
            </div>

            {/* Score Breakdown Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-border/50 dark:border-slate-700/60 text-xs">
              <div className="p-2.5 rounded-lg bg-background dark:bg-slate-900 border border-border/40">
                <span className="text-text-muted block text-[11px]">Winnowing (N-gram)</span>
                <span className="font-semibold text-text-main">{directResult.winnowing_score}%</span>
              </div>
              <div className="p-2.5 rounded-lg bg-background dark:bg-slate-900 border border-border/40">
                <span className="text-text-muted block text-[11px]">Semantic (Neural)</span>
                <span className="font-semibold text-text-main">{directResult.semantic_score}%</span>
              </div>
              <div className="p-2.5 rounded-lg bg-background dark:bg-slate-900 border border-border/40">
                <span className="text-text-muted block text-[11px]">Containment Ratio</span>
                <span className="font-semibold text-text-main">{directResult.containment_score}%</span>
              </div>
              <div className="p-2.5 rounded-lg bg-background dark:bg-slate-900 border border-border/40">
                <span className="text-text-muted block text-[11px]">Line Overlap</span>
                <span className="font-semibold text-text-main">{directResult.match_ratio}%</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Direct Project Comparison */}
      <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-8 shadow-sm">
        <div className="flex items-center gap-3 mb-2">
          <GitCompare className="w-6 h-6 text-primary" />
          <h2 className="text-xl font-bold text-text-main">Direct Project Comparison</h2>
        </div>
        <p className="text-text-muted text-sm mb-6">
          Compare two indexed projects head-to-head and see exactly which files overlap.
        </p>

        <div className="flex flex-col md:flex-row gap-4 w-full">
          <select
            className="flex-1 bg-background dark:bg-slate-900 border border-border dark:border-slate-700 rounded-lg px-4 py-3 focus:ring-2 focus:ring-primary/20 outline-none text-text-main"
            value={projectA}
            onChange={(e) => { setProjectA(e.target.value); setComparisonResult(null); setComparisonError(null); }}
          >
            <option value="">
              {loadingProjects && savedProjects.length === 0 ? "Loading projects..." : "Select Project A..."}
            </option>
            {projectA && !savedProjects.some((p: any) => p.id === projectA) && (
              <option key={`cmp-a-${projectA}`} value={projectA}>{projectA}</option>
            )}
            {savedProjects.map((p: any) => (
              <option key={`cmp-a-${p.id}`} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select
            className="flex-1 bg-background dark:bg-slate-900 border border-border dark:border-slate-700 rounded-lg px-4 py-3 focus:ring-2 focus:ring-primary/20 outline-none text-text-main"
            value={projectB}
            onChange={(e) => { setProjectB(e.target.value); setComparisonResult(null); setComparisonError(null); }}
          >
            <option value="">
              {loadingProjects && savedProjects.length === 0 ? "Loading projects..." : "Select Project B..."}
            </option>
            {projectB && !savedProjects.some((p: any) => p.id === projectB) && (
              <option key={`cmp-b-${projectB}`} value={projectB}>{projectB}</option>
            )}
            {savedProjects.map((p: any) => (
              <option key={`cmp-b-${p.id}`} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button
            disabled={!projectA || !projectB || projectA === projectB || isComparing}
            onClick={runComparison}
            className="bg-primary text-primary-text px-6 py-3 rounded-lg font-medium hover:bg-primary/90 flex items-center justify-center gap-2 disabled:opacity-50 transition-all"
          >
            {isComparing ? <RefreshCw className="w-5 h-5 animate-spin" /> : <GitCompare className="w-5 h-5" />}
            {isComparing ? 'Comparing...' : 'Run Comparison'}
          </button>
        </div>

        {comparisonError && (
          <div className="mt-6 bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-600 dark:text-red-400 text-sm">
            {comparisonError}
          </div>
        )}

        {comparisonResult && (
          <div className="mt-6">
            <div className="text-sm text-text-muted mb-3">
              <span className="font-semibold text-text-main">{comparisonResult.project_a}</span>
              {' vs '}
              <span className="font-semibold text-text-main">{comparisonResult.project_b}</span>
              {' — '}
              {comparisonResult.match_count} matching file pair{comparisonResult.match_count === 1 ? '' : 's'} (≥20% overlap)
            </div>
            {comparisonResult.comparisons.length === 0 ? (
              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-6 text-center">
                <ShieldCheck className="w-8 h-8 text-emerald-600 dark:text-emerald-400 mx-auto mb-2" />
                <p className="font-medium text-emerald-600 dark:text-emerald-400">No overlapping files found!</p>
                <p className="text-sm mt-1 text-text-muted">These two projects share no significant file-level overlap.</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border/50 dark:border-slate-700">
                <table className="w-full text-left text-sm">
                  <thead className="bg-surface/95 dark:bg-slate-800 border-b border-border/50 dark:border-slate-700">
                    <tr>
                      <th className="p-3 font-medium text-text-muted">File in A</th>
                      <th className="p-3 font-medium text-text-muted">File in B</th>
                      <th className="p-3 font-medium text-text-muted">Type</th>
                      <th className="p-3 font-medium text-text-muted">Similarity %</th>
                      <th className="p-3 font-medium text-text-muted">Status</th>
                      <th className="p-3 font-medium text-text-muted text-right">Diff</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50 dark:divide-slate-700">
                    {comparisonResult.comparisons.map((m: ProjectComparisonMatch, i: number) => (
                      <tr key={i} className="hover:bg-surface/50 dark:hover:bg-slate-700/40 transition-colors">
                        <td className="p-3 font-mono text-xs text-text-main">{m.file_a}</td>
                        <td className="p-3 font-mono text-xs text-text-main">{m.file_b}</td>
                        <td className="p-3">
                          <span className={`px-2 py-1 rounded text-xs ${m.type === 'code' ? 'bg-primary/10 text-primary' : 'bg-accent/10 text-accent-text dark:text-accent'}`}>
                            {m.type}
                          </span>
                        </td>
                        <td className="p-3 font-bold text-text-main">{m.similarity}%</td>
                        <td className="p-3">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${
                            m.similarity >= 85 ? 'bg-red-500/10 text-red-600 dark:text-red-400' :
                            m.similarity >= 65 ? 'bg-orange-500/10 text-orange-600 dark:text-orange-400' :
                            m.similarity >= 40 ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400' :
                            'bg-green-500/10 text-green-600 dark:text-green-400'
                          }`}>
                            {m.similarity >= 85 ? 'CRITICAL' : m.similarity >= 65 ? 'HIGH' : m.similarity >= 40 ? 'LOW' : 'SAFE'}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            onClick={() => setDiffTarget(m)}
                            title="View the matching lines side by side"
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border/60 dark:border-slate-600 text-text-muted hover:text-primary hover:border-primary/50 hover:bg-primary/10 transition-colors"
                          >
                            <Eye className="w-4 h-4" />
                            <span className="text-xs font-medium">View Diff</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error Display */}
      {scanError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-5 text-red-600 dark:text-red-400 flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-sm">Scan Notification</div>
              <p className="text-xs mt-0.5 leading-relaxed">{scanError}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => useScanStore.getState().failScan('')}
            className="text-text-muted hover:text-text-main p-1 transition-colors"
            title="Dismiss notification"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Results Section */}
      {scanResult && (
        <>
          <SummaryCards
            scanResult={{
              overall_similarity: scanResult.overall_similarity,
              verdict: scanResult.verdict,
              total_files: scanResult.total_files || (scanResult.code_files_count || 0) + (scanResult.text_files_count || 0),
              code_files_count: scanResult.code_files_count || 0,
              text_files_count: scanResult.text_files_count || 0,
              total_loc: scanResult.total_loc || 0,
              languages_detected: scanResult.languages_detected,
              excluded_files: scanResult.excluded_files,
            }}
            scanDuration={scanDuration}
          />

          <ComparisonsTable
            comparisons={comparisons}
            activeDeepScans={activeDeepScans}
            deepScanResultsCache={deepScanResultsCache}
            onDeepScan={runDeepScan}
            onViewDeepScanResult={(res) => setDeepScanResult(res)}
          />
        </>
      )}

      {/* Scan History Modal */}
      <ScanHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onSelectReport={(report) => {
          setSelectedProject(report.project_name || report.id || "");
        }}
      />

      {/* Deep AI Scan Result Modal */}
      <DeepScanPanel
        deepScanResult={deepScanResult}
        onClose={() => setDeepScanResult(null)}
      />

      {/* Direct Two-File Visual Diff Modal */}
      {showDirectDiffModal && directResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="text-lg font-bold flex items-center gap-2 text-text-main">
                <Eye className="w-5 h-5 text-primary" />
                Pairwise Diff: {directResult.file_a_name} vs {directResult.file_b_name}
              </h3>
              <button
                onClick={() => setShowDirectDiffModal(false)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface/50 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto">
              <DiffViewer
                projectA={directResult.file_a_name}
                fileA={directResult.file_a_name}
                projectB={directResult.file_b_name}
                fileB={directResult.file_b_name}
                initialData={{
                  project_a: "Document A",
                  file_a: directResult.file_a_name,
                  project_b: "Document B",
                  file_b: directResult.file_b_name,
                  similarity: directResult.similarity,
                  lines_a: directResult.lines_a,
                  lines_b: directResult.lines_b,
                  opcodes: directResult.opcodes,
                  matched_lines: directResult.matched_lines,
                  total_lines_a: directResult.total_lines_a,
                  total_lines_b: directResult.total_lines_b,
                  match_ratio: directResult.match_ratio,
                }}
              />
            </div>

            <div className="flex justify-end p-5 border-t border-border">
              <button
                onClick={() => setShowDirectDiffModal(false)}
                className="px-4 py-2 rounded-lg bg-primary text-primary-text font-medium hover:opacity-90 transition-opacity"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Visual Diff Viewer Modal */}
      {diffTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-xl w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="text-lg font-bold flex items-center gap-2 text-text-main">
                <Eye className="w-5 h-5 text-primary" />
                Visual Diff — Matching Lines
              </h3>
              <button
                onClick={() => setDiffTarget(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface/50 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto">
              <DiffViewer
                projectA={comparisonResult?.project_a || projectA}
                fileA={diffTarget.file_a}
                projectB={comparisonResult?.project_b || projectB}
                fileB={diffTarget.file_b}
              />
            </div>

            <div className="flex justify-end p-5 border-t border-border">
              <button
                onClick={() => setDiffTarget(null)}
                className="px-4 py-2 rounded-lg bg-primary text-primary-text font-medium hover:opacity-90 transition-opacity"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
