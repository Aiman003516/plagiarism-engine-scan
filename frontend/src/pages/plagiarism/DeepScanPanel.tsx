import React from 'react';
import { BrainCircuit, X } from 'lucide-react';
import type { DeepScanResult } from '../../lib/api';

export interface DeepScanPanelProps {
  deepScanResult: DeepScanResult | null;
  onClose: () => void;
}

export function DeepScanPanel({ deepScanResult, onClose }: DeepScanPanelProps) {
  if (!deepScanResult) return null;

  const getVerdictStyle = (verdict: string) => {
    switch (verdict?.toUpperCase()) {
      case 'CRITICAL':
      case 'HIGH':
        return 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30';
      case 'LOW':
        return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30';
      case 'SAFE':
      default:
        return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
    }
  };

  const modelDisplayName = (model: string) => {
    if (model === 'unixcoder-base') return 'UniXcoder (Source Code)';
    if (model === 'bge-m3') return 'BGE-M3 (Multilingual & Arabic)';
    if (model === 'all-MiniLM-L6-v2') return 'MiniLM-L6-v2 (Fallback)';
    return model;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="bg-card dark:bg-slate-800 border border-border/60 dark:border-slate-700 rounded-xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-border/50 dark:border-slate-700">
          <h3 className="text-lg font-bold flex items-center gap-2 text-text-main">
            <BrainCircuit className="w-5 h-5 text-primary" />
            AI Semantic Verification
          </h3>
          <button
            onClick={onClose}
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
              {modelDisplayName(deepScanResult.model_used)}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-text-muted mb-1">AI Semantic Similarity Score</div>
            <div className="text-3xl font-bold text-text-main">{deepScanResult.ai_similarity}%</div>
          </div>

          <div>
            <div className="text-xs font-medium text-text-muted mb-2">Verdict</div>
            <span
              className={`inline-block px-3 py-1.5 rounded-full text-sm font-bold border ${getVerdictStyle(
                deepScanResult.verdict
              )}`}
            >
              {deepScanResult.verdict}
            </span>
          </div>

          <div className="pt-2 border-t border-border/50 dark:border-slate-700 space-y-1">
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

        <div className="flex justify-end p-5 border-t border-border/50 dark:border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-primary text-primary-text font-medium hover:opacity-90 transition-opacity"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
