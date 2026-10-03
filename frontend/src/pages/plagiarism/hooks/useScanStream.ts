import { useEffect } from "react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { ScanStreamSession, scanStreamReconnectUrl } from "../../../lib/api";
import { useScanStore } from "../../../lib/scanStore";

// SSE events can span network chunks, including in the middle of a UTF-8 character.
export async function readZipScanStream(
  response: Response,
  onLog: (text: string) => void,
  onSession?: (session: ScanStreamSession) => void
): Promise<any> {
  if (!response.ok) {
    const detail = (await response.text()).trim();
    throw new Error(`ZIP upload failed (${response.status})${detail ? `: ${detail}` : "."}`);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("Expected an SSE response from the ZIP upload endpoint.");
  }
  if (!response.body) {
    throw new Error("Streaming responses are not supported by this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let dataLines: string[] = [];
  let completed = false;
  let finalResult: any = null;

  const dispatchEvent = () => {
    if (dataLines.length === 0) return;
    const data = dataLines.join("\n");
    dataLines = [];

    let event: { type?: string; text?: string; message?: string; result?: any; project_id?: string; stream_token?: string } | null;
    try {
      event = JSON.parse(data);
    } catch {
      throw new Error("Received an invalid JSON event from the ZIP scan stream.");
    }
    if (!event || typeof event !== "object") {
      throw new Error("Received an invalid event from the ZIP scan stream.");
    }

    if (event.type === "session" && event.project_id && event.stream_token) {
      // Reconnect capability: lets the UI re-attach after navigation/reload.
      onSession?.({ project_id: event.project_id, stream_token: event.stream_token });
    } else if (event.type === "log" && typeof event.text === "string") {
      onLog(event.text);
    } else if (event.type === "complete") {
      completed = true;
      finalResult = event.result;
    } else if (event.type === "error") {
      throw new Error(event.message || "The ZIP scan failed.");
    }
  };

  // Handle LF, CRLF and CR line endings without losing a split CRLF pair.
  const consumeLines = (atEnd = false) => {
    let lineEnd: number;
    while (!completed && (lineEnd = buffer.search(/[\r\n]/)) !== -1) {
      if (!atEnd && buffer[lineEnd] === "\r" && lineEnd === buffer.length - 1) break;
      const line = buffer.slice(0, lineEnd);
      const separatorLength = buffer[lineEnd] === "\r" && buffer[lineEnd + 1] === "\n" ? 2 : 1;
      buffer = buffer.slice(lineEnd + separatorLength);

      if (line === "") {
        dispatchEvent();
      } else if (line === "data" || line.startsWith("data:")) {
        dataLines.push(line.slice(5).replace(/^ /, ""));
      }
      // Ignore SSE comments, heartbeats and other fields.
    }
  };

  try {
    while (!completed) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      consumeLines(done);
      if (done) break;
    }
    if (!completed) {
      throw new Error("The ZIP scan stream ended before a completion event was received. Please retry.");
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // A disconnected stream may already be closed or errored.
    }
    reader.releaseLock();
  }
  return finalResult;
}

export function useScanStreamReconnection() {
  const { t } = useTranslation();

  // --- Resume an in-flight scan after navigating away or reloading -------------
  useEffect(() => {
    const {
      isScanning: scanActive,
      activeProjectId,
      streamToken,
      streamLogCount,
      abortController,
    } = useScanStore.getState();
    if (!scanActive || !activeProjectId || !streamToken || abortController) return;

    useScanStore.getState().reconnectScan(activeProjectId);

    // `streamLogCount` tells the backend which lines we already hold, so the replay
    // tops the terminal up instead of duplicating every line on each navigate-back.
    const source = new EventSource(
      scanStreamReconnectUrl(activeProjectId, streamToken, streamLogCount)
    );
    let settled = false;

    const closeStream = () => {
      if (settled) return;
      settled = true;
      source.close();
    };

    source.onmessage = (raw) => {
      let event: { type?: string; text?: string; message?: string; result?: any } | null = null;
      try {
        event = JSON.parse(raw.data);
      } catch {
        return; // Ignore heartbeats / malformed frames.
      }
      if (!event || typeof event !== "object") return;

      if (event.type === "log" && typeof event.text === "string") {
        useScanStore.getState().noteServerLog(event.text);
      } else if (event.type === "complete") {
        closeStream();
        if (event.result) {
          useScanStore.getState().completeScan(event.result);
        } else {
          useScanStore.setState({ isScanning: false, isReconnecting: false, streamToken: null });
        }
        toast.success(t("intake_progress_title") + " ✓");
      } else if (event.type === "error") {
        closeStream();
        const message = event.message || "The resumed scan failed.";
        useScanStore.getState().failScan(message);
        toast.error(message);
      }
      // A "session" frame is ignored here: the token is already in the store.
    };

    source.onerror = () => {
      // Closing right after the terminal frame can also fire `onerror`, so bail out
      // when the scan already settled. Otherwise the stream is genuinely gone
      // (backend restart, session TTL) — stop the browser's endless retry loop and
      // surface it instead of spinning forever.
      if (settled) return;
      closeStream();
      useScanStore.getState().markScanInterrupted(
        "The live scan stream could not be resumed. Check Scan History for the final report."
      );
    };

    return () => {
      // Unmount only drops the connection. The Zustand state — and the scan itself —
      // deliberately survives, so the next mount (or a reload) can resume it again.
      closeStream();
    };
    // Runs once on mount: the decision is made from the persisted store snapshot.
  }, [t]);
}

export const handleStreamSession = (session: ScanStreamSession) => {
  useScanStore.getState().setStreamSession(session.project_id, session.stream_token);
};
