import type { AdminUserView, AnalysisResult, AnalysisSummary, AuthUser, Preferences, RateStatus } from "./types";

const BASE = import.meta.env.VITE_API_BASE || "";

const TOKEN_KEY = "giq-token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export class ApiError extends Error {
  status: number;
  retryAfter?: number;
  constructor(message: string, status: number, retryAfter?: number) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
  } catch {
    /* ignore */
  }
  const ra = res.headers.get("Retry-After");
  return new ApiError(detail, res.status, ra ? Number(ra) : undefined);
}

export async function signup(username: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function me(): Promise<AuthUser> {
  const res = await fetch(`${BASE}/api/auth/me`, { headers: authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function getRate(): Promise<RateStatus> {
  const res = await fetch(`${BASE}/api/auth/rate`, { headers: authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function startAnalysis(
  repoUrl: string,
  preferences: Preferences,
  scopePath = ""
): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ repo_url: repoUrl, preferences, scope_path: scopePath }),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function getRepoTree(
  repoUrl: string
): Promise<{ owner: string; repo: string; dirs: string[] }> {
  const res = await fetch(`${BASE}/api/repo/tree?repo_url=${encodeURIComponent(repoUrl)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/api/analysis/${id}`, { headers: authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function cancelAnalysis(id: string): Promise<AnalysisResult> {
  const res = await fetch(`${BASE}/api/analysis/${id}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function listAnalyses(): Promise<AnalysisSummary[]> {
  const res = await fetch(`${BASE}/api/analyses`, { headers: authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function listAdminUsers(): Promise<AdminUserView[]> {
  const res = await fetch(`${BASE}/api/admin/users`, { headers: authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function ttsAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/tts/config`);
    if (!res.ok) return false;
    return (await res.json()).available === true;
  } catch {
    return false;
  }
}

export async function fetchNarration(text: string): Promise<string> {
  const res = await fetch(`${BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw await parseError(res);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
