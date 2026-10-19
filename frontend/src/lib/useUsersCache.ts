import { useState, useEffect, useCallback } from "react";
import { usersApi, UserProfileData } from "./api";

const memoryCache = new Map<string, UserProfileData[]>();
const listeners = new Map<string, Array<(data: UserProfileData[]) => void>>();
const fetchTimes = new Map<string, number>();
const activeFetches = new Set<string>();

const STALE_TIME_MS = 10000;

function getCacheKey(role?: string): string {
  return role ? `cached_users_${role}` : "cached_users_all";
}

function notify(key: string, data: UserProfileData[]) {
  memoryCache.set(key, data);
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // Ignore storage quota
  }
  const group = listeners.get(key) || [];
  group.forEach((fn) => fn(data));
}

function getInitial(key: string): UserProfileData[] {
  const mem = memoryCache.get(key);
  if (mem && mem.length > 0) return mem;
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        memoryCache.set(key, parsed);
        return parsed;
      }
    }
  } catch {
    // Ignore corrupt storage
  }
  return [];
}

export function useUsersCache(roleFilter?: string) {
  const key = getCacheKey(roleFilter);
  const [users, setUsers] = useState<UserProfileData[]>(() => getInitial(key));
  const [loading, setLoading] = useState<boolean>(() => getInitial(key).length === 0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const initial = getInitial(key);
    setUsers(initial);
    if (initial.length === 0) {
      setLoading(true);
    }

    const listener = (newUsers: UserProfileData[]) => {
      setUsers(newUsers);
      setLoading(false);
      setError(null);
    };

    if (!listeners.has(key)) {
      listeners.set(key, []);
    }
    listeners.get(key)!.push(listener);

    return () => {
      const group = listeners.get(key);
      if (group) {
        listeners.set(key, group.filter((fn) => fn !== listener));
      }
    };
  }, [key]);

  const refresh = useCallback(async (force = false) => {
    const now = Date.now();
    const lastTime = fetchTimes.get(key) || 0;
    const cached = memoryCache.get(key);
    if (!force && cached && cached.length > 0 && now - lastTime < STALE_TIME_MS) {
      return;
    }
    if (activeFetches.has(key)) return;

    activeFetches.add(key);
    if (!cached || cached.length === 0) {
      setLoading(true);
    }

    try {
      const res = await usersApi.getAll(roleFilter ? { role: roleFilter } : undefined);
      const list = res.users || [];
      fetchTimes.set(key, Date.now());
      notify(key, list);
      setError(null);
    } catch (err: any) {
      console.error("Failed to fetch users:", err);
      setError(err?.message || "Failed to load users");
    } finally {
      activeFetches.delete(key);
      setLoading(false);
    }
  }, [key, roleFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    users,
    loading,
    error,
    refresh: () => refresh(true),
  };
}
