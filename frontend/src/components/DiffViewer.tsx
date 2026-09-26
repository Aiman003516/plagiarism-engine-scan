/**
 * DiffViewer — side-by-side visual diff of two stored project files.
 *
 * Loads the line-level diff from `POST /api/plagiarism/compare-files` (raw
 * `difflib` opcodes) and highlights every *equal* line block in red: in a
 * plagiarism review an identical line IS the evidence. `replace`, `insert` and
 * `delete` blocks render normally, and blank filler rows keep the two panes
 * line-for-line aligned.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { plagiarismApi, CompareFilesResult, DiffOpcode } from '../lib/api';

interface DiffViewerProps {
  projectA: string;
  fileA: string;
  projectB: string;
  fileB: string;
}

/** One rendered row: a real source line, or a filler that keeps panes aligned. */
interface DiffRow {
  /** 1-based line number, or null for a filler row. */
  lineNo: number | null;
  text: string;
  /** True when difflib reported this line as identical in both files. */
  matched: boolean;
}

/**
 * Flatten the opcodes into the rows of one pane.
 * `side === 'a'` reads the i1/i2 indexes, `side === 'b'` reads j1/j2.
 */
function buildRows(opcodes: DiffOpcode[], lines: string[], side: 'a' | 'b'): DiffRow[] {
  const rows: DiffRow[] = [];

  opcodes.forEach((opcode) => {
    const [tag, i1, i2, j1, j2] = opcode;
    const from = side === 'a' ? i1 : j1;
    const to = side === 'a' ? i2 : j2;
    const otherFrom = side === 'a' ? j1 : i1;
    const otherTo = side === 'a' ? j2 : i2;

    // Lines this pane actually owns for the current opcode.
    const ownedByThisSide =
      tag === 'equal' ||
      tag === 'replace' ||
      (tag === 'delete' && side === 'a') ||
      (tag === 'insert' && side === 'b');

    if (ownedByThisSide) {
      for (let idx = from; idx < to; idx++) {
        rows.push({ lineNo: idx + 1, text: lines[idx] ?? '', matched: tag === 'equal' });
      }
      // A `replace` block can hold a different number of lines on each side —
      // pad the shorter side so the two panes never drift out of alignment.
      const otherCount = otherTo - otherFrom;
      for (let pad = to - from; pad < otherCount; pad++) {
        rows.push({ lineNo: null, text: '', matched: false });
      }
    } else {
      // The other pane owns this block — pad so both sides stay aligned.
      for (let idx = otherFrom; idx < otherTo; idx++) {
        rows.push({ lineNo: null, text: '', matched: false });
      }
    }
  });

  return rows;
}

function DiffPane({ title, rows }: { title: string; rows: DiffRow[] }) {
  return (
    <div className="flex-1 min-w-0 flex flex-col rounded-lg overflow-hidden border border-border/50 dark:border-slate-700 bg-background dark:bg-slate-900">
      <div className="px-3 py-2 border-b border-border/50 dark:border-slate-700 bg-surface/60 dark:bg-slate-800">
        <div className="font-mono text-xs text-text-main truncate" title={title}>
          {title}
        </div>
      </div>
      <pre className="flex-1 m-0 overflow-auto max-h-[60vh] p-2 font-mono text-xs leading-5 text-text-main">
        {rows.map((row, idx) => (
          <div
            key={idx}
            className={`flex gap-2 px-1 rounded-sm ${
              row.lineNo === null ? 'bg-surface/50 dark:bg-slate-800/50' : ''
            }`}
          >
            <span className="w-9 shrink-0 text-right select-none text-text-muted/70">
              {row.lineNo ?? ''}
            </span>
            {row.matched ? (
              <mark className="flex-1 rounded-sm bg-danger/20 text-danger-text whitespace-pre-wrap break-all">
                {row.text || ' '}
              </mark>
            ) : (
              <span className="flex-1 whitespace-pre-wrap break-all">{row.text || ' '}</span>
            )}
          </div>
        ))}
      </pre>
    </div>
  );
}

export default function DiffViewer({ projectA, fileA, projectB, fileB }: DiffViewerProps) {
  const [data, setData] = useState<CompareFilesResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    plagiarismApi
      .compareFiles({ project_a: projectA, file_a: fileA, project_b: projectB, file_b: fileB })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: any) => {
        if (!cancelled) setError(e?.message || 'Failed to load the diff');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectA, fileA, projectB, fileB]);

  const rowsA = useMemo(() => (data ? buildRows(data.opcodes, data.lines_a, 'a') : []), [data]);
  const rowsB = useMemo(() => (data ? buildRows(data.opcodes, data.lines_b, 'b') : []), [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-text-muted">
        <Loader2 className="w-5 h-5 animate-spin text-primary" />
        <span className="text-sm">Comparing files line by line...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-600 dark:text-red-400 text-sm flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        <span>{error}</span>
      </div>
    );
  }

  if (!data) return null;

  const longestSide = Math.max(data.lines_a.length, data.lines_b.length, 1);
  const copiedPct = Math.round(((data.matched_lines || 0) / longestSide) * 100);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-text-muted">
        <span className="inline-flex items-center gap-2">
          <span className="w-3 h-3 rounded-sm bg-danger/20 border border-danger/40" />
          Identical line (copied)
        </span>
        <span>
          <span className="font-semibold text-text-main">{data.matched_lines}</span> matching lines
          {' · '}
          <span className="font-semibold text-text-main">{copiedPct}%</span> of the longer file
          {' · '}difflib ratio{' '}
          <span className="font-semibold text-text-main">{data.match_ratio}%</span>
        </span>
      </div>

      <div className="flex flex-col lg:flex-row gap-4">
        <DiffPane title={`${projectA} — ${fileA}`} rows={rowsA} />
        <DiffPane title={`${projectB} — ${fileB}`} rows={rowsB} />
      </div>
    </div>
  );
}
