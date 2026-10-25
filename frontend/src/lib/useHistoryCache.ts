import { useState, useEffect, useCallback } from "react";
import { plagiarismApi, PlagiarismHistoryItem } from "./api";

const CACHE_KEY = "cached_scan_history";

let memoryCache: PlagiarismHistoryItem[] | null = null;
let listeners: Array<(data: PlagiarismHistoryItem[]) => void> = [];

function notifyListeners(data: PlagiarismHistoryItem[]) {
  memoryCache = data;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // Ignore quota errors
  }
  listeners.forEach((listener) => listener(data));
}

export function resetHistoryMemoryCache() {
  memoryCache = null;
  try {
    localStorage.removeItem(CACHE_KEY);
  } catch {
    // Ignore storage errors
  }
}

export function invalidateHistoryCache() {
  memoryCache = null;
  lastFetchTime = 0;
}

function getInitialHistory(): PlagiarismHistoryItem[] {
  if (memoryCache && memoryCache.length > 0) {
    return memoryCache;
  }
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        memoryCache = parsed;
        return parsed;
      }
    }
  } catch {
    // Ignore parse error
  }
  return [];
}

let isFetching = false;
let lastFetchTime = 0;
const STALE_TIME_MS = 15000; // 15-second SWR window

export function useHistoryCache() {
  const [historyList, setHistoryList] = useState<PlagiarismHistoryItem[]>(getInitialHistory);
  const [loading, setLoading] = useState<boolean>(() => getInitialHistory().length === 0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const listener = (newList: PlagiarismHistoryItem[]) => {
      setHistoryList(newList);
      setLoading(false);
      setError(null);
    };
    listeners.push(listener);
    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  }, []);

  const refresh = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && memoryCache && now - lastFetchTime < STALE_TIME_MS) {
      setLoading(false);
      return;
    }

    if (isFetching) return;
    isFetching = true;
    if (!memoryCache) {
      setLoading(true);
    }

    try {
      const res = await plagiarismApi.getHistory();
      const list = res.reports || [];
      lastFetchTime = Date.now();
      notifyListeners(list);
    } catch (err: any) {
      setError(err?.message || "Failed to load scan history");
    } finally {
      isFetching = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { historyList, loading, error, refresh };
}
