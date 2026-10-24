import React, { useRef, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Terminal, Copy, Download, Clock, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { useScanStore, ScanSource } from "../../lib/scanStore";

export interface ScanProgressProps {
  scope?: ScanSource;
}

export function ScanProgress({ scope }: ScanProgressProps = {}) {
  const { t } = useTranslation();
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  const isScanning = useScanStore((s) => s.isScanning);
  const scanSource = useScanStore((s) => s.scanSource);
  const scanLogs = useScanStore((s) => s.scanLogs);
  const scanStartedAt = useScanStore((s) => s.scanStartedAt);
  const scanDuration = useScanStore((s) => s.scanDuration);
  const storeLastLogTimestamp = useScanStore((s) => s.lastLogTimestamp);

  const [terminalAutoScroll, setTerminalAutoScroll] = useState(true);
  const [now, setNow] = useState<number>(Date.now());

  // Only auto-scroll the internal terminal container, NEVER the whole document window.
  useEffect(() => {
    if (terminalAutoScroll && terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [scanLogs, terminalAutoScroll]);

  // Tick every second during scanning for accurate elapsed time.
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isScanning) {
      setNow(Date.now());
      interval = setInterval(() => setNow(Date.now()), 1000);
    }
    return () => clearInterval(interval);
  }, [isScanning]);

  // Scope check: prevents cross-talk between Project Intake and Scanner.
  if (scope && scanSource && scanSource !== scope) {
    return null;
  }

  if (!isScanning && scanLogs.length === 0) return null;

  const elapsedSeconds = isScanning && scanStartedAt
    ? Math.max(0, Math.floor((now - scanStartedAt) / 1000))
    : (scanDuration !== null ? Math.round(scanDuration) : 0);

  const formatTimer = (totalSec: number) => {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const effectiveLastLog = storeLastLogTimestamp || scanStartedAt || now;
  const timeSinceLastLog = isScanning ? Math.max(0, now - effectiveLastLog) : 0;

  const copyTerminalLogs = () => {
    navigator.clipboard.writeText(scanLogs.join("\n"));
    toast.success(t("logs_copied"));
  };

  const downloadTerminalLogs = () => {
    const blob = new Blob([scanLogs.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plagiarism-scan-log-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const cancelScan = () => {
    const cancel = useScanStore.getState().abortController;
    if (cancel) cancel.abort();
    useScanStore.getState().resetScan();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface/80 border border-glass-border dark:border-slate-700 rounded-xl overflow-hidden"
    >
      <div className="p-3.5 px-5 bg-surface/80 border-b border-glass-border flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono font-bold text-text-muted flex items-center gap-2">
            <Terminal className="w-4 h-4 text-primary dark:text-accent" />
            {t("live_terminal_title")}
          </span>
          {isScanning && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              {t("live_stream_active")} ({formatTimer(elapsedSeconds)})
            </span>
          )}
          {!isScanning && (scanDuration !== null || elapsedSeconds > 0) && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface border border-glass-border text-[10px] font-mono text-text-muted">
              <Clock className="w-3 h-3 text-primary dark:text-accent" />
              Duration: {scanDuration !== null ? `${scanDuration.toFixed(1)}s` : `${elapsedSeconds}s`}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isScanning && (
            <button
              onClick={cancelScan}
              className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-red-500/10 hover:bg-red-500/20 text-red-600 dark:text-red-400 border border-red-500/20 transition-colors"
              title="Cancel Scan"
            >
              Cancel Scan
            </button>
          )}
          <button
            onClick={() => setTerminalAutoScroll(!terminalAutoScroll)}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-colors ${terminalAutoScroll ? 'bg-accent/20 text-primary dark:text-accent border border-accent/30' : 'bg-surface text-text-muted'}`}
          >
            Auto-Scroll: {terminalAutoScroll ? "ON" : "OFF"}
          </button>
          <button
            onClick={copyTerminalLogs}
            className="p-1.5 rounded-lg bg-surface hover:bg-surface-hover text-text-muted hover:text-text-main transition-colors"
            title={t("copy_logs")}
          >
            <Copy className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={downloadTerminalLogs}
            className="p-1.5 rounded-lg bg-surface hover:bg-surface-hover text-text-muted hover:text-text-main transition-colors"
            title={t("download_logs")}
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => useScanStore.getState().resetScan()}
            disabled={isScanning}
            className="p-1.5 rounded-lg bg-surface hover:bg-red-500/10 text-text-muted hover:text-red-500 transition-colors disabled:opacity-40"
            title="Clear Terminal Output"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div
        ref={terminalContainerRef}
        dir="ltr"
        role="log"
        aria-label={t("live_terminal_title")}
        aria-live="polite"
        aria-relevant="additions text"
        className="p-4 bg-surface text-text-main font-mono text-xs max-h-64 overflow-y-auto space-y-1 leading-relaxed selection:bg-accent/30 text-left"
      >
        {scanLogs.map((log, idx) => {
          const isAst = log.includes("[AST]");
          const isNlp = log.includes("[NLP]");
          const isMinhash = log.includes("[MINHASH]") || log.includes("[LSH]");
          const isGit = log.includes("[GIT]") || log.includes("🐙");
          const isError = log.includes("[ERROR]") || log.includes("❌");
          const isCompleted = log.includes("[COMPLETED]") || log.includes("[DONE]") || log.includes("✅");

          return (
            <div
              key={idx}
              className={`flex items-start gap-2 ${
                isError
                  ? 'text-red-600 dark:text-red-400'
                  : isCompleted
                  ? 'text-emerald-600 dark:text-emerald-400 font-bold'
                  : isAst
                  ? 'text-warning'
                  : isNlp
                  ? 'text-danger'
                  : isGit
                  ? 'text-primary'
                  : isMinhash
                  ? 'text-primary'
                  : 'text-text-muted'
              }`}
            >
              <span className="text-text-muted select-none">&gt;</span>
              <span className="whitespace-pre-wrap break-words min-w-0">{log}</span>
            </div>
          );
        })}
        {isScanning && timeSinceLastLog > 3000 && (
          <div className="flex items-start gap-2">
            <span className="text-text-muted select-none">&gt;</span>
            <span className="text-primary dark:text-accent font-mono">
              Waiting for the next backend update… {Math.floor(timeSinceLastLog / 1000)}s since the last message.
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
