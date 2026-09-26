/**
 * ErrorBoundary — catches render-time crashes (including React.lazy chunk
 * load failures after a redeploy) and shows a fallback card instead of
 * white-screening the whole app.
 */

import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Surface the failure in the console for debugging.
    console.error("[ErrorBoundary] Uncaught render error:", error, errorInfo);
  }

  private handleRetry = () => {
    // Reset the boundary, then do a full reload — this also recovers from
    // stale lazy-chunk load failures after a new deployment.
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-full w-full p-4 md:p-8 bg-background">
          <div
            role="alert"
            className="w-full max-w-lg rounded-2xl border border-red-500/40 bg-red-500/10 p-6 shadow-lg"
          >
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-red-500 flex-shrink-0" />
              <h2 className="text-lg font-bold text-red-500">
                Something went wrong
              </h2>
            </div>
            <p className="mt-3 text-sm text-text-muted">
              The application crashed while rendering this page. Try reloading
              it — this also fixes stale page loads after a new deployment.
            </p>
            {this.state.error?.message && (
              <pre className="mt-4 max-h-32 overflow-y-auto rounded-lg border border-red-500/20 bg-red-950/40 p-3 text-xs text-red-300 whitespace-pre-wrap break-words">
                {this.state.error.message}
              </pre>
            )}
            <button
              type="button"
              onClick={this.handleRetry}
              className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-semibold hover:bg-red-500 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
