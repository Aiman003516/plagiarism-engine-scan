import React, { useState } from 'react';
import { ShieldCheck, AlertTriangle, FileCode2, Clock, FileWarning, ChevronDown, ChevronUp } from 'lucide-react';

export interface SummaryCardsProps {
  scanResult: {
    overall_similarity: number;
    verdict: string;
    total_files: number;
    code_files_count: number;
    text_files_count: number;
    total_loc: number;
    languages_detected?: string[];
    excluded_files?: string[];
  };
  scanDuration: number;
}

export function SummaryCards({ scanResult, scanDuration }: SummaryCardsProps) {
  const [showExcluded, setShowExcluded] = useState(false);
  const verdict = scanResult.verdict?.toUpperCase() || 'SAFE';

  const getVerdictColor = (v: string) => {
    switch (v) {
      case 'SAFE':
        return 'text-green-600 dark:text-green-400';
      case 'LOW':
        return 'text-amber-500 dark:text-amber-400';
      case 'HIGH':
        return 'text-orange-500 dark:text-orange-400';
      case 'CRITICAL':
      default:
        return 'text-red-600 dark:text-red-400';
    }
  };

  const getVerdictBg = (v: string) => {
    switch (v) {
      case 'SAFE':
        return 'bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400';
      case 'LOW':
        return 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400';
      case 'HIGH':
        return 'bg-orange-500/10 border-orange-500/30 text-orange-600 dark:text-orange-400';
      case 'CRITICAL':
      default:
        return 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400';
    }
  };

  const excluded = scanResult.excluded_files || [];

  return (
    <div className="space-y-4">
      {/* 4 Summary Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-card dark:bg-slate-800 border border-border/50 dark:border-slate-700 rounded-xl p-4 text-center shadow-sm">
          <div className={`text-3xl font-bold ${getVerdictColor(verdict)}`}>
            {scanResult.overall_similarity}%
          </div>
          <div className="text-xs text-text-muted mt-1 font-medium">Overall Similarity</div>
        </div>

        <div className="bg-card dark:bg-slate-800 border border-border/50 dark:border-slate-700 rounded-xl p-4 text-center shadow-sm">
          <div className={`text-2xl font-bold flex items-center justify-center gap-2 ${getVerdictColor(verdict)}`}>
            {verdict === 'SAFE' ? (
              <ShieldCheck className="w-6 h-6 text-green-600 dark:text-green-400" />
            ) : (
              <AlertTriangle className={`w-6 h-6 ${getVerdictColor(verdict)}`} />
            )}
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${getVerdictBg(verdict)}`}>
              {verdict}
            </span>
          </div>
          <div className="text-xs text-text-muted mt-1 font-medium">Verdict</div>
        </div>

        <div className="bg-card dark:bg-slate-800 border border-border/50 dark:border-slate-700 rounded-xl p-4 text-center shadow-sm">
          <div className="text-2xl font-bold text-text-main flex items-center justify-center gap-2">
            <FileCode2 className="w-5 h-5 text-primary" />
            {scanResult.total_files}
          </div>
          <div className="text-xs text-text-muted mt-1">
            {scanResult.code_files_count} code · {scanResult.text_files_count} text
          </div>
        </div>

        <div className="bg-card dark:bg-slate-800 border border-border/50 dark:border-slate-700 rounded-xl p-4 text-center shadow-sm">
          <div className="text-2xl font-bold text-text-main flex items-center justify-center gap-2">
            <Clock className="w-5 h-5 text-amber-500 dark:text-amber-400" />
            {scanDuration.toFixed(1)}s
          </div>
          <div className="text-xs text-text-muted mt-1">
            {scanResult.total_loc.toLocaleString()} lines of code
          </div>
        </div>
      </div>

      {/* Excluded Files Banner if any were excluded */}
      {excluded.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/20 dark:border-amber-500/30 rounded-xl p-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-medium text-amber-700 dark:text-amber-400">
              <FileWarning className="w-4 h-4 text-amber-500" />
              <span>
                <strong>{excluded.length} non-scannable file{excluded.length === 1 ? '' : 's'}</strong> excluded by security and scope policy (configs, build artifacts, lockfiles, or oversized files).
              </span>
            </div>
            <button
              onClick={() => setShowExcluded(!showExcluded)}
              className="text-xs font-medium text-amber-700 dark:text-amber-400 hover:underline flex items-center gap-1"
            >
              {showExcluded ? 'Hide details' : 'View excluded files'}
              {showExcluded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
          {showExcluded && (
            <div className="mt-3 pt-3 border-t border-amber-500/20 max-h-40 overflow-y-auto">
              <ul className="text-xs font-mono space-y-1 text-text-muted">
                {excluded.map((f, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="text-amber-500">•</span>
                    <span className="truncate">{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Languages */}
      {scanResult.languages_detected && scanResult.languages_detected.length > 0 && (
        <div className="bg-card dark:bg-slate-800/60 border border-border/50 dark:border-slate-700 rounded-xl p-4 shadow-sm">
          <div className="text-sm font-medium text-text-muted mb-2">Languages Detected</div>
          <div className="flex flex-wrap gap-2">
            {scanResult.languages_detected.map((lang: string) => (
              <span key={lang} className="px-2 py-1 bg-surface/50 border border-border/40 rounded text-xs font-mono">
                {lang}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
