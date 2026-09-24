import React, { useState, useEffect } from 'react';
import { Database, Search, RefreshCw, AlertTriangle, ShieldCheck, FileCode2, FileText, Clock, BarChart3, Loader2, X, BrainCircuit } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { plagiarismApi, DeepScanResult } from '../lib/api';

interface ScanComparison {
  project: string;
  file1: string;
  file2: string;
  similarity: string;
  type: string;
  status: string;
}

interface ScanResult {
  status: string;
  id: string;
  project_name: string;
  overall_similarity: number;
  code_similarity: number;
  text_similarity: number;
  verdict: string;
  threshold: number;
  comparisons: ScanComparison[];
  code_files_count: number;
  text_files_count: number;
  total_files: number;
  total_loc: number;
  languages_detected: string[];
  timestamp: string;
  scan_type: string;
}

export function PlagiarismAnalysis() {
  const [savedProjects, setSavedProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanDuration, setScanDuration] = useState<number>(0);
  const [deepScanLoading, setDeepScanLoading] = useState<string | null>(null);
  const [deepScanResult, setDeepScanResult] = useState<DeepScanResult | null>(null);

  useEffect(() => {
    plagiarismApi.getProjects()
      .then((data: any) => setSavedProjects(data.projects || []))
      .catch(console.error);
  }, []);

  // Run a deep AI semantic scan on a matched file pair.
  // `cmp.project` is the matched project id (other_project_id), and
  // `cmp.file2` is the matched file within that project.
  const runDeepScan = async (cmp: ScanComparison) => {
    if (!scanResult) return;
    const key = `${cmp.file1}::${cmp.file2}`;
    setDeepScanLoading(key);
    try {
      const res = await plagiarismApi.deepScan({
        project_id: scanResult.project_name,
        file1_path: cmp.file1,
        other_project_id: cmp.project,
        file2_path: cmp.file2,
      });
      setDeepScanResult(res);
    } catch (e: any) {
      toast.error(e?.message || 'Deep scan failed');
    } finally {
      setDeepScanLoading(null);
    }
  };

  const runScan = async () => {
    setIsScanning(true);
    setScanResult(null);
    setScanError(null);
    const t0 = Date.now();
    try {
      const res = await plagiarismApi.runScan('Saved Project Scan', selectedProject);
      const duration = ((Date.now() - t0) / 1000);
      setScanDuration(duration);
      console.log('Scan result:', res);
      setScanResult(res as ScanResult);
      toast.success(`Analysis complete in ${duration.toFixed(1)}s`);
    } catch (e: any) {
      setScanError(e.message || 'Unknown error');
      toast.error(e.message);
    }
    setIsScanning(false);
  };

  const comparisons = scanResult?.comparisons || [];

  return (
    <div className="space-y-6 pb-12">
      {/* Scanner Card */}
      <div className="bg-card border border-border/50 rounded-xl p-8 flex flex-col items-center shadow-sm">
        <Database className="w-16 h-16 text-primary mb-4" />
        <h2 className="text-2xl font-bold mb-2">System-Wide Plagiarism Scanner</h2>
        <p className="text-text-muted text-center max-w-lg mb-8">
          Select a project that has already been indexed into the database to instantly run a system-wide plagiarism scan.
        </p>
        <div className="flex gap-4 w-full max-w-md">
          <select 
            className="flex-1 bg-background border border-border rounded-lg px-4 py-3 focus:ring-2 focus:ring-primary/20 outline-none text-text-main"
            value={selectedProject}
            onChange={(e) => { setSelectedProject(e.target.value); setScanResult(null); setScanError(null); }}
          >
            <option value="">Select a saved project...</option>
            {savedProjects.map((p: any) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button 
            disabled={!selectedProject || isScanning}
            onClick={runScan}
            className="bg-primary text-primary-text px-6 py-3 rounded-lg font-medium hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50 transition-all"
          >
            {isScanning ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
            {isScanning ? 'Scanning...' : 'Run Scan'}
          </button>
        </div>
      </div>

      {/* Error Display */}
      {scanError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-400">
          <div className="flex items-center gap-2 font-bold mb-2">
            <AlertTriangle className="w-5 h-5" />
            Scan Failed
          </div>
          <p className="text-sm">{scanError}</p>
        </div>
      )}

      {/* Results */}
      {scanResult && (
        <>
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-card border border-border/50 rounded-xl p-4 text-center">
              <div className={`text-3xl font-bold ${scanResult.verdict === 'SAFE' ? 'text-green-400' : 'text-red-400'}`}>
                {scanResult.overall_similarity}%
              </div>
              <div className="text-xs text-text-muted mt-1">Overall Similarity</div>
            </div>
            <div className="bg-card border border-border/50 rounded-xl p-4 text-center">
              <div className={`text-2xl font-bold flex items-center justify-center gap-2 ${scanResult.verdict === 'SAFE' ? 'text-green-400' : 'text-red-400'}`}>
                {scanResult.verdict === 'SAFE' ? <ShieldCheck className="w-6 h-6" /> : <AlertTriangle className="w-6 h-6" />}
                {scanResult.verdict}
              </div>
              <div className="text-xs text-text-muted mt-1">Verdict</div>
            </div>
            <div className="bg-card border border-border/50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-text-main flex items-center justify-center gap-2">
                <FileCode2 className="w-5 h-5 text-primary" />
                {scanResult.total_files}
              </div>
              <div className="text-xs text-text-muted mt-1">{scanResult.code_files_count} code · {scanResult.text_files_count} text</div>
            </div>
            <div className="bg-card border border-border/50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-text-main flex items-center justify-center gap-2">
                <Clock className="w-5 h-5 text-amber-400" />
                {scanDuration.toFixed(1)}s
              </div>
              <div className="text-xs text-text-muted mt-1">{scanResult.total_loc.toLocaleString()} lines of code</div>
            </div>
          </div>

          {/* Languages */}
          {scanResult.languages_detected && scanResult.languages_detected.length > 0 && (
            <div className="bg-card border border-border/50 rounded-xl p-4">
              <div className="text-sm font-medium text-text-muted mb-2">Languages Detected</div>
              <div className="flex flex-wrap gap-2">
                {scanResult.languages_detected.map((lang: string) => (
                  <span key={lang} className="px-2 py-1 bg-surface/50 rounded text-xs font-mono">{lang}</span>
                ))}
              </div>
            </div>
          )}

          {/* Comparisons Table */}
          <div className="bg-card border border-border/50 rounded-xl p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-primary" />
                Matched Files ({comparisons.length})
              </h3>
            </div>

            {comparisons.length === 0 ? (
              <div className="p-8 text-center text-text-muted bg-surface/20 rounded-lg">
                <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-green-400" />
                <p className="font-medium">No plagiarism matches found!</p>
                <p className="text-sm mt-1">This project appears to be completely original across all indexed projects.</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border/50">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur border-b border-border/50">
                    <tr>
                      <th className="p-3 font-medium text-text-muted">Source File</th>
                      <th className="p-3 font-medium text-text-muted">Matched Project</th>
                      <th className="p-3 font-medium text-text-muted">Matched File</th>
                      <th className="p-3 font-medium text-text-muted">Type</th>
                      <th className="p-3 font-medium text-text-muted">Similarity</th>
                      <th className="p-3 font-medium text-text-muted">Status</th>
                      <th className="p-3 font-medium text-text-muted">AI Verify</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {comparisons.map((cmp: ScanComparison, i: number) => (
                      <tr key={i} className="hover:bg-surface/50 transition-colors">
                        <td className="p-3 font-mono text-xs">{cmp.file1}</td>
                        <td className="p-3 font-medium">{cmp.project}</td>
                        <td className="p-3 font-mono text-xs">{cmp.file2}</td>
                        <td className="p-3">
                          <span className={`px-2 py-1 rounded text-xs ${cmp.type === 'Code' ? 'bg-primary/10 text-primary' : 'bg-accent/10 text-accent-text'}`}>
                            {cmp.type}
                          </span>
                        </td>
                        <td className="p-3 font-bold">{cmp.similarity}</td>
                        <td className="p-3">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${cmp.status === 'FLAGGED' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'}`}>
                            {cmp.status}
                          </span>
                        </td>
                        <td className="p-3">
                          {deepScanLoading === `${cmp.file1}::${cmp.file2}` ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-accent/50 text-accent-text">
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              Scanning
                            </span>
                          ) : (
                            <button
                              onClick={() => runDeepScan(cmp)}
                              className="px-2.5 py-1 rounded text-xs font-semibold bg-primary text-primary-text hover:opacity-90 transition-all flex items-center gap-1"
                              title="🔬 Deep Scan"
                            >
                              🔬 Deep Scan
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Deep AI Scan Result Modal */}
      {deepScanResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-card border border-border rounded-xl w-full max-w-md shadow-lg">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="text-lg font-bold flex items-center gap-2 text-text-main">
                <BrainCircuit className="w-5 h-5 text-primary" />
                AI Semantic Verification
              </h3>
              <button
                onClick={() => setDeepScanResult(null)}
                className="p-1.5 rounded-lg text-text-muted hover:bg-surface/50 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div>
                <div className="text-xs font-medium text-text-muted mb-1">AI Model Used</div>
                <div className="text-base font-semibold text-text-main">
                  {deepScanResult.model_used === 'unixcoder-base'
                    ? 'UniXcoder'
                    : deepScanResult.model_used === 'bge-m3'
                      ? 'BGE-M3'
                      : deepScanResult.model_used}
                </div>
              </div>

              <div>
                <div className="text-xs font-medium text-text-muted mb-1">AI Semantic Similarity Score</div>
                <div className="text-3xl font-bold text-text-main">{deepScanResult.ai_similarity}%</div>
              </div>

              <div>
                <div className="text-xs font-medium text-text-muted mb-2">Verdict</div>
                <span
                  className={`inline-block px-3 py-1.5 rounded-full text-sm font-bold border ${
                    deepScanResult.verdict === 'CONFIRMED_PLAGIARISM'
                      ? 'bg-red-500/10 text-red-400 border-red-500/30'
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  }`}
                >
                  {deepScanResult.verdict}
                </span>
              </div>

              <div className="pt-2 border-t border-border space-y-1">
                <div className="text-xs text-text-muted">
                  <span className="font-medium text-text-main">File 1:</span>{' '}
                  <span className="font-mono break-all">{deepScanResult.file1}</span>
                </div>
                <div className="text-xs text-text-muted">
                  <span className="font-medium text-text-main">File 2:</span>{' '}
                  <span className="font-mono break-all">{deepScanResult.file2}</span>
                </div>
              </div>
            </div>

            <div className="flex justify-end p-5 border-t border-border">
              <button
                onClick={() => setDeepScanResult(null)}
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
