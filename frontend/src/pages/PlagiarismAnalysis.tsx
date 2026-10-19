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
} from '../lib/api';
import DiffViewer from '../components/DiffViewer';
import { SummaryCards } from './plagiarism/SummaryCards';
import { ComparisonsTable } from './plagiarism/ComparisonsTable';
import { DeepScanPanel } from './plagiarism/DeepScanPanel';
import { ScanProgress } from './plagiarism/ScanProgress';
import { useScanStore } from '../lib/scanStore';
import { handleStreamSession } from './plagiarism/hooks/useScanStream';
import { useProjectsCache } from '../lib/useProjectsCache';

export function PlagiarismAnalysis() {
  const location = useLocation();
  const {
    projects: savedProjects,
    loading: loadingProjects,
    error: projectsError,
    refresh: refreshProjects,
  } = useProjectsCache();

  // Persistent scanStore: scan execution & live streaming survive navigation and reloads
  const isScanning = useScanStore((s) => s.isScanning);
  const scanResult = useScanStore((s) => s.scanResult);
  const scanError = useScanStore((s) => s.scanError);
  const activeProjectId = useScanStore((s) => s.activeProjectId);

  const [selectedProject, setSelectedProject] = useState<string>(() => activeProjectId || '');
  const [scanDuration, setScanDuration] = useState<number>(0);
  const [deepScanLoading, setDeepScanLoading] = useState<string | null>(null);
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
          setScanDuration((Date.now() - start) / 1000);
          useScanStore.getState().completeScan(res as PlagiarismScanResult);
        })
        .catch((e) => {
          useScanStore.getState().failScan(e.message || "Failed to load report");
          toast.error("Failed to load report");
        });
    }
  }, [location.search]);

  // Run a deep AI semantic scan on a matched file pair.
  const runDeepScan = async (cmp: PlagiarismComparison) => {
    if (!scanResult) return;
    const file2 = cmp.file2 || cmp.matched_file || '';
    const key = `${cmp.file1}::${file2}`;
    setDeepScanLoading(key);
    try {
      const res = await plagiarismApi.deepScan({
        project_id: scanResult.project_name || scanResult.target || '',
        file1_path: cmp.file1 || '',
        other_project_id: cmp.project,
        file2_path: file2,
      });
      setDeepScanResult(res);
    } catch (e: any) {
      toast.error(e?.message || 'Deep scan failed');
    } finally {
      setDeepScanLoading(null);
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

    useScanStore.getState().startScan(selectedProject);
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
          setScanDuration(duration);
          useScanStore.getState().completeScan(result);
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
      <ScanProgress />

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
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-600 dark:text-red-400">
          <div className="flex items-center gap-2 font-bold mb-2">
            <AlertTriangle className="w-5 h-5" />
            Scan Failed
          </div>
          <p className="text-sm">{scanError}</p>
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
            deepScanLoading={deepScanLoading}
            onDeepScan={runDeepScan}
          />
        </>
      )}

      {/* Deep AI Scan Result Modal */}
      <DeepScanPanel
        deepScanResult={deepScanResult}
        onClose={() => setDeepScanResult(null)}
      />

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
