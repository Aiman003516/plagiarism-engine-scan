import React from "react";

export function TableSkeleton({ columns = 5, rows = 6 }: { columns?: number; rows?: number }) {
  return (
    <div className="w-full overflow-hidden rounded-xl border border-border/60 bg-surface/50 shadow-sm animate-pulse">
      {/* Table Header Skeleton */}
      <div className="flex items-center gap-4 px-5 py-3.5 bg-surface-hover/50 border-b border-border/60">
        {Array.from({ length: columns }).map((_, i) => (
          <div
            key={`th-${i}`}
            className="h-4 bg-text-muted/15 rounded-md"
            style={{ width: i === 0 ? "35%" : `${Math.floor(65 / (columns - 1))}%` }}
          />
        ))}
      </div>

      {/* Table Rows Skeleton */}
      <div className="divide-y divide-border/40">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={`tr-${r}`} className="flex items-center gap-4 px-5 py-4">
            <div className="flex items-center gap-3 w-[35%]">
              <div className="w-8 h-8 rounded-lg bg-text-muted/15 shrink-0" />
              <div className="space-y-1.5 flex-1">
                <div className="h-4 bg-text-muted/20 rounded w-4/5" />
                <div className="h-3 bg-text-muted/10 rounded w-1/2" />
              </div>
            </div>
            {Array.from({ length: columns - 1 }).map((_, c) => (
              <div
                key={`td-${r}-${c}`}
                className="h-4 bg-text-muted/15 rounded"
                style={{ width: `${Math.floor(65 / (columns - 1))}%` }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={`cg-${i}`}
          className="glass-card rounded-2xl p-5 border border-border/60 bg-surface/60 space-y-4"
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-text-muted/15 shrink-0" />
              <div className="space-y-1.5">
                <div className="h-4 bg-text-muted/20 rounded w-32" />
                <div className="h-3 bg-text-muted/10 rounded w-20" />
              </div>
            </div>
            <div className="w-8 h-8 rounded-lg bg-text-muted/10" />
          </div>

          <div className="pt-3 border-t border-border/40 flex items-center justify-between">
            <div className="h-3 bg-text-muted/15 rounded w-24" />
            <div className="h-5 bg-text-muted/20 rounded-full w-20" />
          </div>

          <div className="h-9 bg-text-muted/15 rounded-xl w-full" />
        </div>
      ))}
    </div>
  );
}

export function FormPanelSkeleton() {
  return (
    <div className="glass-panel p-6 rounded-2xl border border-border/60 space-y-6 max-w-2xl mx-auto animate-pulse">
      <div className="space-y-2">
        <div className="h-6 bg-text-muted/25 rounded w-48" />
        <div className="h-4 bg-text-muted/15 rounded w-72" />
      </div>

      <div className="space-y-4 pt-4 border-t border-border/40">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={`field-${i}`} className="space-y-2">
            <div className="h-4 bg-text-muted/20 rounded w-32" />
            <div className="h-10 bg-text-muted/15 rounded-xl w-full" />
          </div>
        ))}
      </div>

      <div className="flex justify-end gap-3 pt-4">
        <div className="h-10 bg-text-muted/15 rounded-xl w-24" />
        <div className="h-10 bg-primary/20 rounded-xl w-32" />
      </div>
    </div>
  );
}
