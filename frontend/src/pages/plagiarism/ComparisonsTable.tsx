import React from 'react';
import { BarChart3, ShieldCheck, Loader2 } from 'lucide-react';
import type { PlagiarismComparison } from '../../lib/api';

export interface ComparisonsTableProps {
  comparisons: PlagiarismComparison[];
  deepScanLoading: string | null;
  onDeepScan: (cmp: PlagiarismComparison) => void;
}

export function ComparisonsTable({ comparisons, deepScanLoading, onDeepScan }: ComparisonsTableProps) {
  const renderWhyBadge = (cmp: PlagiarismComparison) => {
    if (cmp.embedded_copy || (cmp.containment_score && cmp.containment_score >= 0.8)) {
      const containmentPct = cmp.containment_score ? `${Math.round(cmp.containment_score * 100)}%` : '>=80%';
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
    switch (status) {
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

  return (
    <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-primary" />
          Matched Files ({comparisons.length})
        </h3>
      </div>

      {comparisons.length === 0 ? (
        <div className="p-8 text-center text-text-muted bg-surface/20 rounded-lg">
          <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-green-600 dark:text-green-400" />
          <p className="font-medium">No plagiarism matches found!</p>
          <p className="text-sm mt-1">This project appears to be completely original across all indexed projects.</p>
        </div>
      ) : (
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
              {comparisons.map((cmp, i) => {
                const scanKey = `${cmp.file1}::${cmp.file2}`;
                const isLoadingThis = deepScanLoading === scanKey;

                return (
                  <tr key={i} className="hover:bg-surface/50 dark:hover:bg-slate-700/40 transition-colors">
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
                      {isLoadingThis ? (
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
      )}
    </div>
  );
}
