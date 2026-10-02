/**
 * Unified API Client for the Ministry Plagiarism Engine.
 * Connects the frontend Vite React to the FastAPI backend (http://127.0.0.1:8000).
 */

export const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || "http://127.0.0.1:8000";

/**
 * First frame of every scan stream. Carries the per-scan capability token that
 * authorises re-attaching to a still-running scan over
 * `GET /api/plagiarism/scan-stream/{project_id}` — the endpoint an `EventSource`
 * resumes on after the user navigates away or reloads. `EventSource` can neither
 * POST nor send an `Authorization` header, hence the token in the query string.
 */
export interface ScanStreamSession {
  project_id: string;
  stream_token: string;
  reconnect_url?: string;
}

/** Absolute `EventSource` URL used to resume listening to a running scan.
 *  `after` is the number of log lines the client already has, so the server only
 *  replays what was missed instead of duplicating the whole terminal. */
export const scanStreamReconnectUrl = (projectId: string, streamToken: string, after = 0): string => {
  const cursor = Math.max(0, Math.floor(after) || 0);
  return `${API_BASE_URL}/api/plagiarism/scan-stream/${encodeURIComponent(projectId)}`
    + `?token=${encodeURIComponent(streamToken)}&after=${cursor}`;
};

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(message: string, status: number, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = "ApiError";
  }
}

export async function apiFetch<T = any>(endpoint: string, options: RequestInit & { signal?: AbortSignal } = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string> || {}),
  };

  const token = localStorage.getItem("auth_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), 600000);
  const signal = options.signal && typeof AbortSignal.any === "function"
    ? AbortSignal.any([options.signal, timeoutController.signal])
    : timeoutController.signal;

  try {
    const res = await fetch(url, { ...options, headers, signal });
    const isJson = res.headers.get("content-type")?.includes("application/json");
    let data: any = null;
    try {
      data = isJson ? await res.json() : await res.text();
    } catch {
      data = null;
    }

    if (!res.ok) {
      const errorMsg = typeof data === "object" && data?.detail
        ? String(data.detail)
        : typeof data === "string" && data.trim()
          ? data
          : `Request failed with HTTP ${res.status}`;
      // A 401 from login (bad credentials) or change-password (wrong current
      // password) is a form error, not an expired session — never force logout,
      // otherwise the forced password-change screen ejects the user on a typo.
      const isAuthFormError =
        endpoint.startsWith("/api/auth/login") ||
        endpoint.startsWith("/api/auth/change-password");
      if (res.status === 401 && !isAuthFormError) {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("user_data");
        window.dispatchEvent(new CustomEvent("auth-expired"));
      }
      throw new ApiError(errorMsg, res.status, data);
    }

    return data as T;
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    if (err?.name === "AbortError") {
      throw new ApiError("The request timed out. Please check the backend and try again.", 408);
    }
    throw new ApiError(
      "Unable to reach the backend. Start the API server or check VITE_API_URL.",
      0,
      err
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
}

// ============================================================================
// Auth & RBAC API
// ============================================================================
export interface AuthUser {
  id: string;
  name: string;
  /** Email for staff/admin accounts; the enrollment number for students. */
  email: string;
  role: string;
  /** Present on student accounts — their login identity. */
  enrollment_number?: string | null;
  college_id?: string | null;
  /** When true the account must rotate its password before using the app. */
  requires_password_change?: boolean;
  created_at?: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface ChangePasswordResponse {
  detail: string;
  requires_password_change: boolean;
  /** Freshly issued JWT with the forced password-change flag cleared. */
  token: string;
}

export const authApi = {
  /**
   * `identifier` is the single login field: an email for staff/admin accounts
   * or an enrollment number for students. It is sent as `email`, the
   * backwards-compatible alias the backend resolves against both tables.
   */
  login: (identifier: string, password: string) =>
    apiFetch<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: identifier, password }),
    }),

  me: () => apiFetch<AuthUser>("/api/auth/me"),

  changePassword: (oldPassword: string, newPassword: string) =>
    apiFetch<ChangePasswordResponse>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword,
      }),
    }),
};


// ============================================================================
// Plagiarism & Similarity Scanner API
// ============================================================================
export interface PlagiarismComparison {
  project: string;
  matched_file?: string;
  university?: string;
  similarity: string;
  type: string;
  status: "Safe" | "Moderate" | "FLAGGED";
  submitted_snippet?: string;
  matched_snippet?: string;
  file1?: string;
  file2?: string;
  loc_matched?: number;
}

export interface GitCommitInfo {
  sha: string;
  author: string;
  date: string;
  message: string;
}

export interface GitContributorInfo {
  name: string;
  commits_count: string;
}

export interface GitMetadata {
  repo_url: string;
  branch: string;
  commits: GitCommitInfo[];
  contributors: GitContributorInfo[];
  commit_sha: string;
}

export interface PlagiarismScanResult {
  status: string;
  id?: string;
  target?: string;
  project_name?: string;
  scan_type: string;
  overall_similarity: number;
  code_similarity: number;
  text_similarity: number;
  verdict: "SAFE" | "FLAGGED";
  threshold: number;
  comparisons: PlagiarismComparison[];
  logs?: string[];
  git_metadata?: GitMetadata;
  code_files_count?: number;
  text_files_count?: number;
  total_files?: number;
  total_loc?: number;
  languages_detected?: string[];
  timestamp: string;
}

export interface PlagiarismHistoryItem {
  id: string;
  project_name: string;
  scan_type: string;
  overall_similarity: number;
  code_similarity: number;
  text_similarity: number;
  verdict: "SAFE" | "FLAGGED";
  total_files: number;
  total_loc: number;
  timestamp: string;
}

export interface GitRepoScanPayload {
  repo_url: string;
  branch?: string;
  access_token?: string;
  project_name?: string;
  scan_type?: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  title?: string | null;
  abstract?: string | null;
  team_id?: string | null;
  department?: string | null;
  year?: number | null;
  university?: string | null;
  status?: 'pending' | 'approved' | 'rejected';
  student_id?: string;
  created_at?: string;
}

export interface ProjectFile {
  project_id: string;
  relative_path: string;
  file_type: string;
  content: string;
}

export interface DeepScanResult {
  ai_similarity: number;
  model_used: string;
  method: string;
  verdict: string;
  file1: string;
  file2: string;
}

export interface DeepScanPayload {
  project_id: string;
  file1_path: string;
  other_project_id: string;
  file2_path: string;
}

export interface ProjectComparisonPayload {
  project_a: string;
  project_b: string;
}

export interface ProjectComparisonMatch {
  file_a: string;
  file_b: string;
  similarity: number;
  type: string;
}

export interface ProjectComparisonResult {
  status: string;
  project_a: string;
  project_b: string;
  match_count: number;
  comparisons: ProjectComparisonMatch[];
}

export interface CompareFilesPayload {
  project_a: string;
  file_a: string;
  project_b: string;
  file_b: string;
}

/** One `difflib` opcode: [tag, i1, i2, j1, j2] where tag is equal/replace/insert/delete. */
export type DiffOpcode = [string, number, number, number, number];

export interface CompareFilesResult {
  project_a: string;
  project_b: string;
  file_a: string;
  file_b: string;
  lines_a: string[];
  lines_b: string[];
  opcodes: DiffOpcode[];
  matched_lines: number;
  match_ratio: number;
}

export const plagiarismApi = {
  getProjects: () =>
    apiFetch<{ projects: ProjectSummary[] }>("/api/plagiarism/projects"),

  updateProject: (id: string, updates: Partial<ProjectSummary>) =>
    apiFetch<ProjectSummary>(`/api/plagiarism/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  deleteProject: (id: string) =>
    apiFetch<{ detail: string }>(`/api/plagiarism/projects/${id}`, {
      method: "DELETE",
    }),

  approveProject: (id: string) =>
    apiFetch<{ detail: string }>(`/api/plagiarism/projects/${id}/approve`, {
      method: "POST",
    }),

  getProjectFiles: (id: string) =>
    apiFetch<{ files: ProjectFile[] }>(`/api/plagiarism/projects/${id}/files`),

  checkProjectExists: (names: string[]) =>
    apiFetch<string[]>(`/api/plagiarism/projects/check?names=${encodeURIComponent(names.join(','))}`),

  runScan: (scanType: string, target?: string) =>
    apiFetch<PlagiarismScanResult>("/api/plagiarism/scan", {
      method: "POST",
      body: JSON.stringify({
        scan_type: scanType,
        target: target,
      }),
    }),

  uploadAndScan: (projectName: string, files: Array<{ file?: File; path?: string; content?: string }>, scanType = "project") => {
    const formData = new FormData();
    formData.append("project_name", projectName);
    formData.append("scan_type", scanType);
    files.forEach(f => {
      if (f.file) formData.append("files", f.file);
      else if (f.content && f.path) formData.append("files", new Blob([f.content]), f.path);
    });
    return apiFetch<PlagiarismScanResult>("/api/plagiarism/upload-scan", {
      method: "POST",
      body: formData,
    });
  },

  uploadAndScanStream: async (
    projectName: string,
    files: Array<{ file?: File; path?: string; content?: string }>,
    scanType = "Direct Upload Project Scan",
    onLog: (logText: string) => void,
    onComplete: (result: PlagiarismScanResult) => void,
    onError: (errorText: string) => void,
    signal?: AbortSignal,
    onSession?: (session: ScanStreamSession) => void
  ) => {
    const url = `${API_BASE_URL}/api/plagiarism/upload-scan-stream`;
    const token = localStorage.getItem("auth_token");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const formData = new FormData();
    formData.append("project_name", projectName);
    formData.append("scan_type", scanType);
    files.forEach(f => {
      if (f.file) formData.append("files", f.file);
      else if (f.content && f.path) formData.append("files", new Blob([f.content]), f.path);
    });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600000);

    try {
      const res = await fetch(url, {
        method: "POST",
        headers,
        body: formData,
        signal: signal || controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const errText = await res.text();
        try {
          const parsed = JSON.parse(errText);
          throw new Error(parsed.detail || errText);
        } catch {
          throw new Error(errText || `HTTP error ${res.status}`);
        }
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream in response");

      const decoder = new TextDecoder();
      let buffer = "";
      let streamCompleted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (trimmed.startsWith("data:")) {
            const jsonStr = trimmed.replace(/^data:\s*/, "");
            try {
              const msg = JSON.parse(jsonStr);
              if (msg.type === "session" && msg.stream_token) {
                // Reconnect capability: lets the UI re-attach after navigation/reload.
                onSession?.(msg as ScanStreamSession);
              } else if (msg.type === "log" && msg.text) {
                onLog(msg.text);
              } else if (msg.type === "complete" && msg.result) {
                streamCompleted = true;
                onComplete(msg.result);
              } else if (msg.type === "error" && msg.message) {
                streamCompleted = true;
                onError(msg.message);
              }
            } catch (e) {
              console.error("SSE parse error", e, block);
            }
          }
        }
      }
      if (!streamCompleted) {
        onError("Stream ended unexpectedly. The backend may have encountered an error.");
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      onError(err?.message || "Streaming connection failed");
    }
  },

  uploadZipStream: async (
    projectName: string,
    zipFile: File,
    onLog: (logText: string) => void,
    onComplete: (result: PlagiarismScanResult) => void,
    onError: (errorText: string) => void,
    signal?: AbortSignal,
    onSession?: (session: ScanStreamSession) => void
  ) => {
    const url = `${API_BASE_URL}/api/plagiarism/upload-zip-stream`;
    const token = localStorage.getItem("auth_token");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const formData = new FormData();
    formData.append("project_name", projectName);
    formData.append("file", zipFile);

    try {
      const res = await fetch(url, {
        method: "POST",
        headers,
        body: formData,
        signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        try {
          const parsed = JSON.parse(errText);
          throw new Error(parsed.detail || errText);
        } catch {
          throw new Error(errText || `HTTP error ${res.status}`);
        }
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream in response");

      const decoder = new TextDecoder();
      let buffer = "";
      let streamCompleted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (trimmed.startsWith("data:")) {
            const jsonStr = trimmed.replace(/^data:\s*/, "");
            try {
              const msg = JSON.parse(jsonStr);
              if (msg.type === "session" && msg.stream_token) {
                // Reconnect capability: lets the UI re-attach after navigation/reload.
                onSession?.(msg as ScanStreamSession);
              } else if (msg.type === "log" && msg.text) {
                onLog(msg.text);
              } else if (msg.type === "complete" && msg.result) {
                streamCompleted = true;
                onComplete(msg.result);
              } else if (msg.type === "error" && msg.message) {
                streamCompleted = true;
                onError(msg.message);
              }
            } catch (e) {
              console.error("SSE parse error", e, block);
            }
          }
        }
      }
      if (!streamCompleted) {
        onError("Stream ended unexpectedly. The backend may have encountered an error.");
      }
    } catch (err: any) {
      onError(err?.message || "Streaming connection failed");
    }
  },

  scanGitRepo: (payload: GitRepoScanPayload) =>
    apiFetch<PlagiarismScanResult>("/api/plagiarism/git-scan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  scanGitRepoStream: async (
    payload: GitRepoScanPayload,
    onLog: (logText: string) => void,
    onComplete: (result: PlagiarismScanResult) => void,
    onError: (errorText: string) => void,
    signal?: AbortSignal,
    onSession?: (session: ScanStreamSession) => void
  ) => {
    const url = `${API_BASE_URL}/api/plagiarism/git-scan-stream`;
    const token = localStorage.getItem("auth_token");
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        try {
          const parsed = JSON.parse(errText);
          throw new Error(parsed.detail || errText);
        } catch {
          throw new Error(errText || `HTTP error ${res.status}`);
        }
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream in response");

      const decoder = new TextDecoder();
      let buffer = "";
      let streamCompleted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (trimmed.startsWith("data:")) {
            const jsonStr = trimmed.replace(/^data:\s*/, "");
            try {
              const msg = JSON.parse(jsonStr);
              if (msg.type === "session" && msg.stream_token) {
                // Reconnect capability: lets the UI re-attach after navigation/reload.
                onSession?.(msg as ScanStreamSession);
              } else if (msg.type === "log" && msg.text) {
                onLog(msg.text);
              } else if (msg.type === "complete" && msg.result) {
                streamCompleted = true;
                onComplete(msg.result);
              } else if (msg.type === "error" && msg.message) {
                streamCompleted = true;
                onError(msg.message);
              }
            } catch (e) {
              console.error("SSE parse error", e, block);
            }
          }
        }
      }
      if (!streamCompleted) {
        onError("Stream ended unexpectedly. The backend may have encountered an error.");
      }
    } catch (err: any) {
      onError(err?.message || "Git Streaming connection failed");
    }
  },

  deepScan: (payload: DeepScanPayload) =>
    apiFetch<DeepScanResult>("/api/plagiarism/deep-scan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  compareProjects: (payload: ProjectComparisonPayload) =>
    apiFetch<ProjectComparisonResult>("/api/plagiarism/compare-projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Line-level diff (difflib opcodes) of two stored files for the Diff Viewer. */
  compareFiles: (payload: CompareFilesPayload) =>
    apiFetch<CompareFilesResult>("/api/plagiarism/compare-files", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getHistory: () =>
    apiFetch<{ reports: PlagiarismHistoryItem[] }>("/api/plagiarism/history"),

  getHistoryDetail: (reportId: string) =>
    apiFetch<PlagiarismScanResult>(`/api/plagiarism/history/${reportId}`),

  deleteHistory: (reportId: string) =>
    apiFetch<{ status: string; message: string }>(`/api/plagiarism/history/${reportId}`, {
      method: "DELETE",
    }),
};

// ============================================================================
// Users & RBAC API
// ============================================================================
export interface UserProfileData {
  id: string;
  name: string;
  email: string;
  role: string;
  college_id?: string | null;
  created_at?: string;
}

export const usersApi = {
  getAll: (params?: { role?: string; college_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.role) q.append("role", params.role);
    if (params?.college_id) q.append("college_id", params.college_id);
    const queryString = q.toString();
    return apiFetch<{ users: UserProfileData[] }>(`/api/users${queryString ? `?${queryString}` : ""}`);
  },

  getById: (id: string) =>
    apiFetch<UserProfileData>(`/api/users/${id}`),

  create: (data: { name: string; email: string; password: string; role: string; college_id?: string }) =>
    apiFetch<UserProfileData>("/api/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (
    id: string,
    updates: { name?: string; email?: string; password?: string; role?: string; college_id?: string }
  ) =>
    apiFetch<UserProfileData>(`/api/users/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  delete: (id: string) =>
    apiFetch<{ detail: string }>(`/api/users/${id}`, {
      method: "DELETE",
    }),
};

// ============================================================================
// Teams API
// ============================================================================
export interface TeamMemberData {
  id: string;
  enrollment_number: string;
  name: string;
  college_id?: string | null;
  team_id?: string | null;
  created_at?: string;
}

export interface TeamData {
  id: string;
  name: string;
  college_id?: string | null;
  created_at?: string;
  members?: TeamMemberData[];
}

export const teamsApi = {
  getAll: (collegeId?: string) => {
    const q = collegeId ? `?college_id=${encodeURIComponent(collegeId)}` : "";
    return apiFetch<{ teams: TeamData[] }>(`/api/teams${q}`);
  },

  getById: (id: string) => apiFetch<TeamData>(`/api/teams/${id}`),

  create: (data: { name: string; college_id?: string }) =>
    apiFetch<TeamData>("/api/teams", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: { name: string }) =>
    apiFetch<TeamData>(`/api/teams/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<{ detail: string }>(`/api/teams/${id}`, {
      method: "DELETE",
    }),

  addMember: (teamId: string, enrollmentNumber: string) =>
    apiFetch<{ members: TeamMemberData[] }>(`/api/teams/${teamId}/members`, {
      method: "POST",
      body: JSON.stringify({ enrollment_number: enrollmentNumber }),
    }),

  removeMember: (teamId: string, studentId: string) =>
    apiFetch<{ detail: string }>(`/api/teams/${teamId}/members/${studentId}`, {
      method: "DELETE",
    }),
};

// ============================================================================
// Dashboard Stats API
// ============================================================================
export interface DashboardStats {
  total_projects: number;
  total_teams: number;
  total_users: number;
  total_files: number;
  recent_scans: Array<Record<string, any>>;
  flagged_count: number;
}

export const dashboardApi = {
  stats: () => apiFetch<DashboardStats>("/api/dashboard/stats"),
};

// ============================================================================
// Settings & Preferences API
// ============================================================================
export type SettingsMap = Record<string, any>;

export const settingsApi = {
  getAll: () => apiFetch<SettingsMap>("/api/settings"),

  update: (settings: SettingsMap) =>
    apiFetch<SettingsMap>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};

// ============================================================================
// System Health & Analytics Summary
// ============================================================================
export const systemHealthApi = {
  get: () => apiFetch<{
    status: string;
    timestamp?: string;
    database?: string;
    biometrics?: string;
    plagiarism?: string;
    models_ready?: boolean;
  }>("/api/system/health"),
};
