import React, { useState, useMemo } from 'react';
import { BarChart3, ShieldCheck, Loader2, Search, ChevronLeft, ChevronRight, Filter } from 'lucide-react';
import type { PlagiarismComparison } from '../../lib/api';

export interface ComparisonsTableProps {
  comparisons: PlagiarismComparison[];
  deepScanLoading?: string | null;
  activeDeepScans?: string[];
  deepScanResultsCache?: Record<string, any>;
  onDeepScan: (cmp: PlagiarismComparison) => void;
  onViewDeepScanResult?: (res: any) => void;
}

export function ComparisonsTable({
  comparisons,
  deepScanLoading,
  activeDeepScans = [],
  deepScanResultsCache = {},
  onDeepScan,
  onViewDeepScanResult,
}: ComparisonsTableProps) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'CRITICAL' | 'HIGH' | 'LOW' | 'SAFE'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const renderWhyBadge = (cmp: PlagiarismComparison) => {
    const rawCont = cmp.containment_score ?? 0;
    const contPct = rawCont > 1 ? rawCont : rawCont * 100;
    if (cmp.embedded_copy || contPct >= 80) {
      const containmentPct = contPct > 0 ? `${Math.round(contPct)}%` : '>=80%';
      return (
        <span
          className="inline-flex items-center gap-1 text-[11px] font-medium text-purple-600 dark:text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20"
          title={`Containment score: ${containmentPct}`}
        >
          Embedded copy ({containmentPct})
        </span>
      );
    }
    if (cmp.shared_fingerprints !== undefined && cmp.shared_fingerprints > 0) {
      return (
        <span
          className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-600 dark:text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20"
          title={`${cmp.shared_fingerprints} shared Winnowing fingerprints`}
        >
          Lexical ({cmp.shared_fingerprints} fps)
        </span>
      );
    }
    if (cmp.semantic_score && cmp.semantic_score > 0) {
      return (
        <span
          className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20"
          title="Admitted by neural semantic similarity"
        >
          Semantic match
        </span>
      );
    }
    if (cmp.rule) {
      return <span className="text-[11px] text-text-muted">{cmp.rule}</span>;
    }
    return <span className="text-[11px] text-text-muted">—</span>;
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-red-600/10 text-red-600 dark:text-red-400 border border-red-500/20';
      case 'HIGH':
        return 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20';
      case 'LOW':
        return 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20';
      case 'SAFE':
      default:
        return 'bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20';
    }
  };

  // Filtered comparisons
  const filtered = useMemo(() => {
    return comparisons.filter((c) => {
      if (statusFilter !== 'ALL' && c.status?.toUpperCase() !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const f1 = (c.file1 || '').toLowerCase();
        const proj = (c.project || '').toLowerCase();
        const f2 = (c.file2 || c.matched_file || '').toLowerCase();
        return f1.includes(q) || proj.includes(q) || f2.includes(q);
      }
      return true;
    });
  }, [comparisons, statusFilter, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedComparisons = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  return (
    <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <h3 className="text-lg font-bold flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-primary" />
          Matched Files ({comparisons.length})
        </h3>

        {/* Search and Filters */}
        {comparisons.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                placeholder="Filter by filename or project..."
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
                className="w-full bg-surface dark:bg-slate-900 border border-border/60 rounded-lg pl-8 pr-3 py-1.5 text-xs text-text-main placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            <div className="flex items-center gap-1 bg-surface dark:bg-slate-900 border border-border/60 rounded-lg p-0.5 text-xs">
              {(['ALL', 'CRITICAL', 'HIGH', 'LOW', 'SAFE'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => { setStatusFilter(s); setPage(1); }}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    statusFilter === s
                      ? 'bg-primary text-primary-text'
                      : 'text-text-muted hover:text-text-main'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              className="bg-surface dark:bg-slate-900 border border-border/60 rounded-lg px-2 py-1.5 text-xs text-text-main focus:outline-none"
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
            </select>
          </div>
        )}
      </div>

      {comparisons.length === 0 ? (
        <div className="p-8 text-center text-text-muted bg-surface/20 rounded-lg">
          <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-green-600 dark:text-green-400" />
          <p className="font-medium">No plagiarism matches found!</p>
          <p className="text-sm mt-1">This project appears to be completely original across all indexed projects.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-8 text-center text-text-muted bg-surface/20 rounded-lg">
          <p className="font-medium">No matches match your filter criteria.</p>
          <button
            onClick={() => { setStatusFilter('ALL'); setSearchQuery(''); }}
            className="text-xs text-primary hover:underline mt-2 inline-block"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border/50 dark:border-slate-700">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 bg-surface/95 dark:bg-slate-800 backdrop-blur border-b border-border/50 dark:border-slate-700">
                <tr>
                  <th className="p-3 font-medium text-text-muted">Source File</th>
                  <th className="p-3 font-medium text-text-muted">Matched Project</th>
                  <th className="p-3 font-medium text-text-muted">Matched File</th>
                  <th className="p-3 font-medium text-text-muted">Type</th>
                  <th className="p-3 font-medium text-text-muted">Similarity</th>
                  <th className="p-3 font-medium text-text-muted">Status</th>
                  <th className="p-3 font-medium text-text-muted">Why</th>
                  <th className="p-3 font-medium text-text-muted text-right">AI Verify</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50 dark:divide-slate-700">
                {pagedComparisons.map((cmp, i) => {
                  const scanKey = `${cmp.project}::${cmp.file1}::${cmp.file2 || cmp.matched_file}`;
                  const isLoadingThis = deepScanLoading === scanKey;
                  const isScanningThis = isLoadingThis || (activeDeepScans ? activeDeepScans.includes(scanKey) : false);
                  const cachedResult = deepScanResultsCache ? deepScanResultsCache[scanKey] : undefined;

                  return (
                    <tr key={`${cmp.file1}-${cmp.project}-${cmp.file2}-${i}`} className="hover:bg-surface/50 dark:hover:bg-slate-700/40 transition-colors">
                      <td className="p-3 font-mono text-xs">{cmp.file1}</td>
                      <td className="p-3 font-medium">{cmp.project}</td>
                      <td className="p-3 font-mono text-xs">{cmp.file2 || cmp.matched_file}</td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs ${
                          cmp.type?.toLowerCase() === 'code'
                            ? 'bg-primary/10 text-primary'
                            : 'bg-accent/10 text-accent-text dark:text-accent'
                        }`}>
                          {cmp.type}
                        </span>
                      </td>
                      <td className="p-3">
                        {cmp.winnowing_score !== undefined ? (
                          <div className="flex flex-col gap-1.5 w-36">
                            <div className="flex items-center gap-2 text-[10px]" title="Winnowing: Exact copy-paste detection">
                              <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
                                <div className="bg-blue-500 h-full" style={{ width: `${cmp.winnowing_score}%` }} />
                              </div>
                              <span className="w-8 text-right font-medium text-blue-600 dark:text-blue-400">{cmp.winnowing_score}%</span>
                            </div>
                            <div className="flex items-center gap-2 text-[10px]" title="Semantic: Paraphrasing & meaning match">
                              <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
                                <div className="bg-purple-500 h-full" style={{ width: `${cmp.semantic_score}%` }} />
                              </div>
                              <span className="w-8 text-right font-medium text-purple-600 dark:text-purple-400">{cmp.semantic_score}%</span>
                            </div>
                            <div className="flex items-center gap-2 text-[10px]" title={`Fusion: Combined score (alpha=${cmp.alpha ?? 0.6})`}>
                              <div className="w-full bg-border rounded-full h-1.5 overflow-hidden">
                                <div className="bg-orange-500 h-full" style={{ width: `${cmp.fusion_score}%` }} />
                              </div>
                              <span className="w-8 text-right font-bold text-orange-600 dark:text-orange-400">{cmp.fusion_score}%</span>
                            </div>
                          </div>
                        ) : (
                          <span className="font-bold">{cmp.similarity}</span>
                        )}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${getStatusBadge(cmp.status)}`}>
                          {cmp.status}
                        </span>
                      </td>
                      <td className="p-3">
                        {renderWhyBadge(cmp)}
                      </td>
                      <td className="p-3 text-right">
                        {cachedResult ? (
                          <button
                            onClick={() => (onViewDeepScanResult ? onViewDeepScanResult(cachedResult) : onDeepScan(cmp))}
                            className="px-2.5 py-1 rounded text-xs font-semibold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-all inline-flex items-center gap-1"
                            title="View AI verified semantic similarity"
                          >
                            ✓ AI Verified ({cachedResult.ai_similarity}%)
                          </button>
                        ) : isScanningThis ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-accent/50 text-accent-text">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Scanning
                          </span>
                        ) : (
                          <button
                            onClick={() => onDeepScan(cmp)}
                            className="px-2.5 py-1 rounded text-xs font-semibold bg-primary text-primary-text hover:opacity-90 transition-all inline-flex items-center gap-1"
                            title="Run AI Semantic Deep Scan"
                          >
                            🔬 Deep Scan
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex items-center justify-between mt-4 text-xs text-text-muted">
            <span>
              Showing {filtered.length === 0 ? 0 : (currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, filtered.length)} of {filtered.length} matches
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={currentPage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded-lg border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
              >
                <ChevronLeft className="w-3.5 h-3.5" /> Prev
              </button>
              <span>{currentPage} / {totalPages}</span>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded-lg border border-border hover:bg-surface disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
              >
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
