import { useState, useEffect, useCallback } from "react";
import { teamsApi, TeamData } from "./api";

const CACHE_KEY = "cached_teams_list";

let memoryCache: TeamData[] | null = null;
let listeners: Array<(data: TeamData[]) => void> = [];

function notifyListeners(data: TeamData[]) {
  memoryCache = data;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // Ignore storage quota or disabled storage errors
  }
  listeners.forEach((listener) => listener(data));
}

function getInitialTeams(): TeamData[] {
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

export function useTeamsCache() {
  const [teams, setTeams] = useState<TeamData[]>(getInitialTeams);
  const [loading, setLoading] = useState<boolean>(() => getInitialTeams().length === 0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const listener = (newTeams: TeamData[]) => {
      setTeams(newTeams);
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
      const res = await teamsApi.getAll();
      const list = res.teams || [];
      lastFetchTime = Date.now();
      notifyListeners(list);
      setError(null);
    } catch (err: any) {
      console.error("Failed to fetch teams:", err);
      setError(err?.message || "Failed to load teams");
    } finally {
      isFetching = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    teams,
    loading,
    error,
    refresh: () => refresh(true),
  };
}
