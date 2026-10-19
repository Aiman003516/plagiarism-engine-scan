import { useState, useEffect, useCallback } from "react";
import { plagiarismApi, ProjectSummary } from "./api";

const CACHE_KEY = "cached_saved_projects";

// In-memory module cache: provides instantaneous 0ms responses across route switches
let memoryCache: ProjectSummary[] | null = null;
let listeners: Array<(data: ProjectSummary[]) => void> = [];

function notifyListeners(data: ProjectSummary[]) {
  memoryCache = data;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // Ignore storage quota or disabled storage errors
  }
  listeners.forEach((listener) => listener(data));
}

function getInitialProjects(): ProjectSummary[] {
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
    // Ignore corrupted cache
  }
  return [];
}

let isFetching = false;
let lastFetchTime = 0;
const STALE_TIME_MS = 10000; // 10-second SWR window

export function useProjectsCache() {
  const [projects, setProjects] = useState<ProjectSummary[]>(getInitialProjects);
  const [loading, setLoading] = useState<boolean>(() => getInitialProjects().length === 0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const listener = (newProjects: ProjectSummary[]) => {
      setProjects(newProjects);
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
    if (!force && memoryCache && memoryCache.length > 0 && now - lastFetchTime < STALE_TIME_MS) {
      return;
    }
    if (isFetching) return;

    isFetching = true;
    if (!memoryCache || memoryCache.length === 0) {
      setLoading(true);
    }

    try {
      const res = await plagiarismApi.getProjects();
      const list = res.projects || [];
      lastFetchTime = Date.now();
      notifyListeners(list);
      setError(null);
    } catch (err: any) {
      console.error("Failed to fetch projects:", err);
      setError(err?.message || "Failed to load projects");
    } finally {
      isFetching = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    projects,
    loading,
    error,
    refresh: () => refresh(true),
  };
}
